import os, webbrowser, getpass, StringIO, logging, time
import tornado.web, tornado.ioloop, tornado.websocket, tornado.httpserver

from apiclient.http import HttpError

from circuitscape.compute import Compute
from circuitscape.cfg import CSConfig
from circuitscape.io import CSIO
from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author
from circuitscape import __file__ as cs_pkg_file

from cfg import ServerConfig
from common import PageHandlerBase, ErrorHandler, Utils, AsyncRunner, BaseMsg, WebSocketLogger
from session import SessionInMemory as Session
from cloudauth import GoogleHandler as AuthHandler
from cloudstore import GoogleDriveHandler as StorageHandler
from cloudstore import GoogleDriveStore

SRVR_CFG = None

class WSMsg(BaseMsg):
    REQ_AUTH = 1000
    RSP_AUTH = 1001
    
    REQ_FILE_LIST = 1
    RSP_FILE_LIST = 2
    
    REQ_LOGOUT = 3
    RSP_LOGOUT = 4
    
    REQ_RUN_VERIFY = 5
    RSP_RUN_VERIFY = 6
    
    REQ_RUN_JOB = 7
    RSP_RUN_JOB = 8
    
    REQ_LOAD_CFG = 9
    RSP_LOAD_CFG = 10
    
    REQ_ABORT_JOB = 11
    RSP_ABORT_JOB = 12


class CircuitscapeRunner(AsyncRunner):
    def __init__(self, wslogger, wsmsg, method, *args):
        super(CircuitscapeRunner, self).__init__(wslogger, wsmsg, method, *args)
    
    def completed(self):
        if (None != self.wslogger) and (None != self.wslogger.dest):
            self.wslogger.dest.task = None
    
    @staticmethod
    def check_role_limits(roles, cfg, qlogger):
        if "admin" in roles:
            return (True, None)
        
        try:
            # check max parallel
            qlogger.send_log_msg("Parallelization requested: " + str(cfg.parallelize))
            if cfg.parallelize:
                qlogger.send_log_msg("Parallel processes requested: " + (str(cfg.max_parallel) if (cfg.max_parallel > 0) else "maximum"))
                if cfg.max_parallel == 0:
                    cfg.max_parallel = 20
                else:
                    return (False, "Your profile is restricted to a maximum of 20 parallel processors.")
            
            # check for cumulative maps
            qlogger.send_log_msg("Output maps required for - voltage: " + str(cfg.write_volt_maps) + ", current: " + str(cfg.write_cur_maps) + ", cumulative only: " + str(cfg.write_cum_cur_map_only))
            if cfg.write_volt_maps or (cfg.write_cur_maps and (not cfg.write_cum_cur_map_only)):
                return (False, "Your profile is restricted to create only cumulative current maps.")
            
            # check problem size
            prob_sz = CSIO.problem_size(cfg.data_type, cfg.habitat_file)
            qlogger.send_log_msg("Habitat size: " + str(prob_sz))
            if prob_sz > 24000000:
                return (False, "Your profile is restricted for habitat sizes of 24m nodes only.")
        except Exception as e:
            return (False, "Unknown error verifying limits. (" + str(e) + "). Please check your input files.")
        
        return (True, None)
    
    @staticmethod
    def run_job(qlogger, msg_type, roles, msg_data, work_dir, storage_creds, store_in_cloud):
        solver_failed = True
        output_cloud_folder = None
        output_folder = None
        cfg = CSConfig()
        store = GoogleDriveStore(storage_creds) if (None != storage_creds) else None
        
        for key in msg_data.keys():
            val = msg_data[key]
            if store_in_cloud and (key in CSConfig.FILE_PATH_PROPS) and (val != None):
                # if val is gdrive location, translate it to local drive
                if val.startswith("gdrive://"):
                    if key == 'output_file':
                        # store the output gdrive folder
                        qlogger.send_log_msg("Preparing cloud store output folder: " + val)
                        output_cloud_folder = val
                        output_folder = os.path.join(work_dir, 'output')
                        if not os.path.exists(output_folder):
                            os.mkdir(output_folder)
                        val = os.path.join(output_folder, 'results.out')
                    else:
                        # copy the file locally
                        qlogger.send_log_msg("Reading from cloud store: " + val)
                        val = store.copy_to_local(val, work_dir)
            cfg.__setattr__(key, val)
        
        qlogger.send_log_msg("Verifying configuration...")
        (all_options_valid, message) = cfg.check()
        
        if all_options_valid:
            qlogger.send_log_msg("Verifying profile limits...")
            (all_options_valid, message) = CircuitscapeRunner.check_role_limits(roles, cfg, qlogger)
            
        if not all_options_valid:
            qlogger.send_error_msg(message)
        else:
            # In cloud mode, this would be a temporary directory
            outdir, _out_file = os.path.split(cfg.output_file)
            
            try:
                qlogger.send_log_msg("Storing final configuration...")
                configFile = os.path.join(outdir, 'circuitscape.ini')
                cfg.write(configFile)
    
                cs = Compute(configFile, qlogger)
                result, solver_failed = cs.compute()
                qlogger.send_log_msg("Result: \n" + str(result))
            except Exception as e:
                message = str(e)
                qlogger.send_error_msg(message)

        success = not solver_failed
        
        if success and store_in_cloud:
            qlogger.send_log_msg("Compressing results for upload...")
            output_folder_zip = os.path.join(work_dir, 'output.zip')
            Utils.compress_folder(output_folder, output_folder_zip)
            
            for attempt in range(1,4):
                qlogger.send_log_msg("Uploading results to cloud store...")
                if None == store.copy_to_remote(output_cloud_folder, output_folder_zip, 'application/zip'):
                    qlogger.send_log_msg("Error uploading output.zip. attempt " + str(attempt) + " of 3")
                    time.sleep(5)
                else:
                    break
            
#             for root, _dirs, files in os.walk(output_folder, topdown=False):
#                 for name in files:
#                     outfile = os.path.join(root, name)
#                     qlogger.send_log_msg("uploading " + name + "...")
#                     if None == store.copy_to_remote(output_cloud_folder, outfile):
#                         qlogger.send_log_msg("error uploading " + name)
            qlogger.send_log_msg("Uploaded results to cloud store")
        
        qlogger.send_result_msg(msg_type, {'complete': True, 'success': success})
                    
    
    @staticmethod
    def run_verify(qlogger, msg_type, roles):
        outdir = None
        cwd = os.getcwd()
        strio = StringIO.StringIO()
        try:
            root_path = os.path.dirname(cs_pkg_file)
            outdir = Utils.mkdtemp(prefix="verify_")
            if os.path.exists(root_path):
                root_path = os.path.split(root_path)[0]
                os.chdir(root_path)     # otherwise we are running inside a packaged folder and resources are availale at cwd
            from circuitscape.verify import cs_verifyall
            testResult = cs_verifyall(out_path=outdir, ext_logger=qlogger, stream=strio)
            testsPassed = testResult.wasSuccessful()
        except Exception as e:
            qlogger.send_log_msg("Error during verify: " + str(e))
            testsPassed = False
        finally:
            os.chdir(cwd)
            if None != outdir:
                for root, dirs, files in os.walk(outdir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                os.rmdir(outdir)

        qlogger.send_log_msg(strio.getvalue())
        strio.close()
        qlogger.send_result_msg(msg_type, {'complete': True, 'success': testsPassed})
    

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        self.is_authenticated = False
        logger.debug("websocket connection opened")
            
    def on_close(self):
        self.is_authenticated = False
        logger.debug("websocket connection closed")

#     def dump(self, obj):
#         for attr in dir(obj):
#             print "obj.%s = %s" % (attr, getattr(obj, attr))
    
    def on_message(self, message):
        global SRVR_CFG
        #logger.debug("got request url " + self.request.full_url())
        #logger.debug("websocket message received [%s]"%(str(message),))
        wsmsg = WSMsg(msg=message, handler=self)
        is_shutdown_msg = False
        response = {}
        try:
            if SRVR_CFG.multiuser and not self.is_authenticated:
                response, is_shutdown_msg = self.handle_auth(wsmsg)
            else:            
                if (wsmsg.msg_type() == WSMsg.REQ_FILE_LIST) and not SRVR_CFG.multiuser:
                    response, is_shutdown_msg = self.handle_file_list(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_LOGOUT):
                    response, is_shutdown_msg = self.handle_logout(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_RUN_VERIFY):
                    response, is_shutdown_msg = self.handle_run_verify(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_RUN_JOB):
                    response, is_shutdown_msg = self.handle_run_job(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_ABORT_JOB):
                    response, is_shutdown_msg = self.handle_abort_job(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_LOAD_CFG):
                    response, is_shutdown_msg = self.handle_load_config(wsmsg)

            if response != None:
                logger.debug("responding with message: " + str(response))
                wsmsg.reply(response)
        except Exception:
            logger.exception("Exception handling message of type %d"%(wsmsg.msg_type(),))
            wsmsg.error(-1)
            
        if is_shutdown_msg:
            if SRVR_CFG.multiuser:
                if self.sess != None:
                    self.sess.logout()
                    self.sess = None
            else:
                stop_webserver()

    def handle_auth(self, wsmsg):
        if (not self.is_authenticated) and (wsmsg.msg_type() == WSMsg.REQ_AUTH):
            self.sess_id = wsmsg.data('sess_id')
            self.sess = sess = Session.get_session(self.sess_id)
            self.is_authenticated = (sess != None)
            if self.is_authenticated:
                self.work_dir = sess.work_dir()
                self.storage_creds, self.store = sess.storage()
            return ({'success': self.is_authenticated}, not self.is_authenticated)
        return (None, not self.is_authenticated)
        

    def handle_load_config(self, wsmsg):
        global SRVR_CFG
        result = None
        success = False
        try:
            filepath = wsmsg.data('filename')
            logger.debug("handle_load_config filepath: " + filepath)
            if SRVR_CFG.multiuser:
                logger.debug("translating filepath to local in multiuser mode")
                filepath = self.store.copy_to_local(filepath, self.work_dir)
            logger.debug("handle_load_config filepath: " + filepath)
            
            cfg = CSConfig(filepath)
            
            if SRVR_CFG.multiuser:
                result = cfg.as_dict()
            else:
                filedir, _filename = os.path.split(filepath)
                result = cfg.as_dict(rel_to_abs=filedir)
            success = True
        except Exception as e:
            logger.exception("Error reading configuration from %s"%(wsmsg.data('filename'),))
            result = 'HttpError' if isinstance(e, HttpError) else 'UnknownError'
        logger.debug("returning config [" + str(result) + "]")
        return ({'cfg': result, 'success': success}, False)

    def handle_abort_job(self, wsmsg):
        if self.task != None:
            self.task.abort()
        return (None, False)

    def handle_run_job(self, wsmsg):
        global SRVR_CFG
        wslogger = WebSocketLogger(self)
        multiuser = SRVR_CFG.multiuser
        if multiuser:
            work_dir = self.work_dir
            storage_creds = self.storage_creds
        else:
            work_dir = storage_creds = None
        self.task = CircuitscapeRunner(wslogger, wsmsg, CircuitscapeRunner.run_job, self.sess.user_role(), wsmsg.nv['data'], work_dir, storage_creds, multiuser)
        return (None, False)


    def handle_run_verify(self, wsmsg):
        wslogger = WebSocketLogger(self)
        self.task = CircuitscapeRunner(wslogger, wsmsg, CircuitscapeRunner.run_verify, self.sess.user_role())
        return (None, False)


    def handle_logout(self, wsmsg):
        if SRVR_CFG.multiuser and (self.sess != None):
            self.sess.logout()
            self.sess = None
        return ({}, True)

    def handle_file_list(self, wsmsg):
        filelist = [('..', True)]
        curdir = wsmsg.data('cwd', os.getcwd());
        newdir = wsmsg.data('dir')
        if newdir:
            curdir = os.path.normpath(os.path.join(curdir, newdir));
        for fname in os.listdir(curdir):
            full_fname = os.path.join(curdir, fname)
            is_dir = os.path.isdir(full_fname)
            #print (fname, is_dir)
            filelist.append((fname, is_dir))
        return ({'filelist': filelist, 'dir': curdir}, False)

    

class IndexPageHandler(PageHandlerBase):
    def get(self):
        #logger.debug("got request url " + self.request.full_url())
        global SRVR_CFG
        if SRVR_CFG.multiuser:
            self.sess_id = sess_id = Session.extract_session_id(self)
            self.sess = sess = Session.get_session(sess_id)
            if self.sess == None:
                logger.debug("redirecting request to home page")
                self.redirect('/static/index.html')
                #logger.debug("redirecting request for authentication")
                #self.redirect('/auth/login')
                return
            username = sess.user_name()
            userid = sess.user_id()
            userrole = sess.user_role()
            txt_shutdown = "Logout"
            txt_shutdown_msg = "Are you sure you want to logout from Circuitscape?"
            filedlg_type = "google"
            filedlg_developer_key = SRVR_CFG.cfg_get("GOOGLE_DEVELOPER_KEY")
            filedlg_app_id = SRVR_CFG.cfg_get("GOOGLE_CLIENT_ID")
        else:
            userid = username = getpass.getuser()
            userrole = ['standalone']
            txt_shutdown = "Shutdown"
            txt_shutdown_msg = "Are you sure you want to close Circuitscape?"
            filedlg_type = "srvr"
            filedlg_developer_key = None
            filedlg_app_id = None
            sess_id = ''
        
        kwargs = {
                  'username': username,
                  'userid': userid,
                  'userrole': userrole,
                  'version': cs_version,
                  'author': cs_author,
                  'ws_url': SRVR_CFG.ws_url,
                  'sess_id': sess_id,
                  'txt_shutdown': txt_shutdown,
                  'txt_shutdown_msg': txt_shutdown_msg,
                  'filedlg_type': filedlg_type,
                  'filedlg_developer_key': filedlg_developer_key,
                  'filedlg_app_id': filedlg_app_id
        }
        self.render("cs.html", **kwargs)


    def get_error_html(self, status_code, **kwargs):
        return self.generic_write_error(status_code, message="Error serving your request.")


class Application(tornado.web.Application):
    def __init__(self):
        global SRVR_CFG
        pkgpath, _fname = os.path.split(__file__)
        templates_path = os.path.join(pkgpath, 'templates')
        static_path = os.path.join(pkgpath, 'templates/static')
        ext_path = os.path.join(pkgpath, 'ext')
        handlers = [
            (r'/', IndexPageHandler),
            (ServerConfig.SERVER_WS_PATH, WebSocketHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': static_path}),
            (r'/ext/(.*)', tornado.web.StaticFileHandler, {'path': ext_path})
        ]
        
        if SRVR_CFG.multiuser:
            Session.srvr_cfg = SRVR_CFG
            SRVR_CFG.cfg_set("GOOGLE_STORAGE_AUTH_REDIRECT_URI", SRVR_CFG.storage_auth_redirect_uri)
            StorageHandler.init(SRVR_CFG)
            handlers.append((ServerConfig.SERVER_LOGIN_AUTH_PATH, AuthHandler))
            handlers.append((ServerConfig.SERVER_STORAGE_AUTH_PATH, StorageHandler))

        settings = {
            'template_path': templates_path,
            'debug': True,
            "cookie_secret": SRVR_CFG.cfg_get("SECURE_SALT"),
            "error_handler": ErrorHandler,
        }
        tornado.web.Application.__init__(self, handlers, **settings)

def stop_webserver(from_signal=False):
    ioloop = tornado.ioloop.IOLoop.instance()
    if from_signal:
        ioloop.add_callback_from_signal(lambda x: x.stop(), ioloop)
    else:
        ioloop.add_callback(lambda x: x.stop(), ioloop)

def run_webgui(config):
    global SRVR_CFG
    global logger
    SRVR_CFG = ServerConfig(config)
    
    Utils.temp_files_root = SRVR_CFG.cfg_get("temp_dir", str, None)
    log_lvl = SRVR_CFG.cfg_get("log_level", str, "DEBUG")
    log_lvl = getattr(logging, log_lvl)
    log_file = SRVR_CFG.cfg_get("log_file", str, None)
    
    logger = logging.getLogger('cloudCS')
    tornado_access_logger = logging.getLogger('tornado.access')
    tornado_application_logger = logging.getLogger('tornado.application')
    tornado_general_logger = logging.getLogger('tornado.general')
    
    logger.setLevel(log_lvl)
    tornado_access_logger.setLevel(log_lvl)
    tornado_application_logger.setLevel(log_lvl)
    tornado_general_logger.setLevel(log_lvl)
    
    if log_file:
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s', '%m/%d/%Y %I.%M.%S.%p')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        tornado_access_logger.addHandler(handler)
        tornado_application_logger.addHandler(handler)
        tornado_general_logger.addHandler(handler)
    else:
        logging.basicConfig()

    logger.info('starting up...')
    logger.debug("listening on: " + SRVR_CFG.listen_ip + ':' + str(SRVR_CFG.port))
    logger.debug("hostname: " + SRVR_CFG.host)
    logger.debug("multiuser: " + str(SRVR_CFG.multiuser))
    logger.debug("headless: " + str(SRVR_CFG.headless))

    AsyncRunner.DEFAULT_REPLY = {'complete': True, 'success': False}
    AsyncRunner.LOG_MSG = WSMsg.SHOW_LOG

    BaseMsg.logger = logger
    server = tornado.httpserver.HTTPServer(Application())
    server.listen(SRVR_CFG.port, address=SRVR_CFG.listen_ip)
    if not SRVR_CFG.headless:
        webbrowser.open(SRVR_CFG.http_url)
    
    try:
        tornado.ioloop.IOLoop.instance().start()
    except:
        logger.exception("server shutdown with exception")
        
    logger.info("shutting down...")
    try:
        Session.logout_all()
    except:
        logger.exception("exception while cleaning up")
    logger.info("server shut down")

