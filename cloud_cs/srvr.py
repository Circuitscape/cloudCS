import os, webbrowser, getpass, logging
import tornado.web, tornado.ioloop, tornado.httpserver
#import tornado.websocket 
import sockjs.tornado

from apiclient.http import HttpError

from circuitscape.cfg import CSConfig
from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author

from cfg import ServerConfig
from common import PageHandlerBase, ErrorHandler, Utils, AsyncRunner, BaseMsg, WebSocketLogger
from session import SessionInMemory as Session, SessionStandalone
from cloudauth import GoogleHandler as AuthHandler
from cloudstore import GoogleDriveHandler as StorageHandler
from runner import CircuitscapeRunner

SRVR_CFG = None
websock_router = None

class WSMsg(BaseMsg):
    REQ_AUTH = 1000
    RSP_AUTH = 1001
    
    REQ_FILE_LIST = 101
    RSP_FILE_LIST = 102
    
    REQ_LOGOUT = 103
    RSP_LOGOUT = 104
    
    REQ_RUN_VERIFY = 105
    RSP_RUN_VERIFY = 106
    
    REQ_RUN_JOB = 107
    RSP_RUN_JOB = 108
    
    REQ_LOAD_CFG = 109
    RSP_LOAD_CFG = 110
    
    REQ_ABORT_JOB = 111
    RSP_ABORT_JOB = 112

    REQ_RUN_BATCH = 113
    RSP_RUN_BATCH = 114

    REQ_DETACH_TASK = 115
    RSP_DETACH_TASK = 116
    
    REQ_ATTACH_TASK = 117
    RSP_ATTACH_TASK = 118
    
    REQ_DETACHED_TASKS = 119
    RSP_DETACHED_TASKS = 120
    
    REQ_LAST_RUN_LOG = 121
    RSP_LAST_RUN_LOG = 122


class WebSocketHandler(sockjs.tornado.SockJSConnection):    
    def on_open(self, info):
        global logger
        self.is_authenticated = False
        if not SRVR_CFG.multiuser:
            self.sess = SessionStandalone(getpass.getuser())
        logger.debug("websocket connection opened")

    def on_close(self):
        global logger
        self.is_authenticated = False
        logger.debug("websocket connection closed")
        
        sess = self.sess
        if (sess != None) and (sess.task != None) and sess.detach:
            logger.debug("detaching task")
            self.sess.task.detach()

    def logout_or_detach(self):
        sess = self.sess
        if SRVR_CFG.multiuser and (sess != None):
            logger.debug("in logout_or_detach detach=" + str(sess.detach) + " task:" + str(sess.task == None))
            if (not sess.detach) or (sess.task == None):
                sess.logout()
                self.sess = None
        

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
                elif (wsmsg.msg_type() == WSMsg.REQ_RUN_BATCH):
                    response, is_shutdown_msg = self.handle_run_batch(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_ABORT_JOB):
                    response, is_shutdown_msg = self.handle_abort_job(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_LOAD_CFG):
                    response, is_shutdown_msg = self.handle_load_config(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_DETACH_TASK):
                    response, is_shutdown_msg = self.handle_detach_task(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_ATTACH_TASK):
                    response, is_shutdown_msg = self.handle_attach_task(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_DETACHED_TASKS):
                    response, is_shutdown_msg = self.handle_detached_tasks(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_LAST_RUN_LOG):
                    response, is_shutdown_msg = self.handle_last_run_log(wsmsg)

            if response != None:
                logger.debug("responding with message: " + str(response))
                wsmsg.reply(response)
        except Exception:
            logger.exception("Exception handling message of type %d"%(wsmsg.msg_type(),))
            wsmsg.error(-1)
            
        if is_shutdown_msg:
            if SRVR_CFG.multiuser:
                self.logout_or_detach()
            else:
                stop_webserver()

    def handle_auth(self, wsmsg):
        if (not self.is_authenticated) and (wsmsg.msg_type() == WSMsg.REQ_AUTH):
            self.sess_id = wsmsg.data('sess_id')
            self.sess = sess = Session.get_session(self.sess_id)
            self.is_authenticated = (sess != None)
            if self.is_authenticated:
                sess.detach = True  # set detach mode by default
                self.work_dir = sess.work_dir()
                self.storage_creds, self.store = sess.storage()
                msg = None
            else:
                msg = 'Your login session appears to have timed out. Please sign in again.'
            return ({'success': self.is_authenticated, 'msg': msg}, not self.is_authenticated)
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


    def handle_attach_task(self, wsmsg):
        self.sess.detach = True
        task = self.sess.task
        if None != task:
            wsmsg.reply({'success': True, 'client_ctx': task.client_ctx})
            task.attach(self)
            return (None, False)
        return ({'success': False}, False)


    def handle_detached_tasks(self, wsmsg):
        num_tasks = 1 if (self.sess.task != None) else 0
        return ({'success': True, 'num_tasks': num_tasks}, False)
    

    def handle_detach_task(self, wsmsg):
        self.sess.detach = True
        return ({'success': True}, False)

    def handle_last_run_log(self, wsmsg):
        run_log = Utils.open_last_run_log("", self.sess.user_id())
        if None == run_log:
            return ({'success': False, 'msg': "No run logs found."}, False)
        
        resp_nv = {
                   'msg_type': BaseMsg.SHOW_LOG,
                   'data': ''
        }
        success = False
        try:
            for line in run_log.readlines():
                resp_nv['data'] = line.rstrip()
                self.send(resp_nv, False)
            success = True
        finally:
            run_log.close()
        return ({'success': success}, False)

    def handle_abort_job(self, wsmsg):
        if self.sess.task != None:
            self.sess.task.abort()
        return (None, False)


    def _make_wslogger(self):
        wslogger = WebSocketLogger(self)
        if SRVR_CFG.multiuser:
            tee_file = open(os.path.join(self.sess.local_work_dir, "run.log"), "w")
            wslogger.tee(tee_file)
        return wslogger


    def handle_run_job(self, wsmsg):
        if self.sess.task != None:
            wsmsg.error("Your background task is still running. Wait for it to complete before starting another.")
            return (None, False)
        
        global SRVR_CFG
        wslogger = self._make_wslogger()
        multiuser = SRVR_CFG.multiuser
        if multiuser:
            work_dir = self.work_dir
            storage_creds = self.storage_creds
            user_role = self.sess.user_role()
        else:
            work_dir = storage_creds = None
            user_role = 'standalone'
            
        data = wsmsg.nv['data']
        run_data = data['run_data']
        client_ctx = data['client_ctx']
        self.sess.task = CircuitscapeRunner(wslogger, wsmsg, CircuitscapeRunner.run_job, client_ctx, user_role, run_data, work_dir, storage_creds, multiuser)
        return (None, False)


    def handle_run_batch(self, wsmsg):
        if self.sess.task != None:
            wsmsg.error("Your background task is still running. Wait for it to complete before starting another.")
            return (None, False)
        
        global SRVR_CFG
        wslogger = self._make_wslogger()
        multiuser = SRVR_CFG.multiuser
        if multiuser:
            work_dir = self.work_dir
            storage_creds = self.storage_creds
            user_role = self.sess.user_role()
        else:
            work_dir = storage_creds = None
            user_role = 'standalone'
            
        data = wsmsg.nv['data']
        run_data = data['run_data']
        client_ctx = data['client_ctx']
        self.sess.task = CircuitscapeRunner(wslogger, wsmsg, CircuitscapeRunner.run_batch, client_ctx, user_role, run_data, work_dir, storage_creds, multiuser)
        return (None, False)


    def handle_run_verify(self, wsmsg):
        if self.sess.task != None:
            wsmsg.error("Your background task is still running. Wait for it to complete before starting another.")
            return (None, False)
        
        global SRVR_CFG
        wslogger = self._make_wslogger()
        user_role = self.sess.user_role() if SRVR_CFG.multiuser else 'standalone'
        
        data = wsmsg.nv['data']
        client_ctx = data['client_ctx']
        self.sess.task = CircuitscapeRunner(wslogger, wsmsg, CircuitscapeRunner.run_verify, client_ctx, user_role)
        return (None, False)


    def handle_logout(self, wsmsg):
        self.logout_or_detach()
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
        global logger
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
            has_running_task = (None != sess.task)
            txt_shutdown = "Logout"
            txt_shutdown_msg = "Are you sure you want to logout from Circuitscape?"
            filedlg_type = "google"
            filedlg_developer_key = SRVR_CFG.cfg_get("GOOGLE_DEVELOPER_KEY")
            filedlg_app_id = SRVR_CFG.cfg_get("GOOGLE_CLIENT_ID")
        else:
            userid = username = getpass.getuser()
            userrole = ['standalone']
            has_running_task = False
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
                  'has_running_task': has_running_task,
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
        return self.generic_get_error_html(status_code, message="Error serving your request.")


class Application(tornado.web.Application):
    def __init__(self):
        global SRVR_CFG, websock_router
        pkgpath, _fname = os.path.split(__file__)
        templates_path = os.path.join(pkgpath, 'templates')
        static_path = os.path.join(pkgpath, 'templates/static')
        ext_path = os.path.join(pkgpath, 'ext')
        
        websock_router = sockjs.tornado.SockJSRouter(WebSocketHandler, ServerConfig.SERVER_WS_PATH)
        handlers = [
            (r'/', IndexPageHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': static_path}),
            (r'/ext/(.*)', tornado.web.StaticFileHandler, {'path': ext_path})
        ] + websock_router.urls
        
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

    @staticmethod
    def check_sess_and_task_timeouts():
        global logger
        #logger.debug("checking task timeouts")
        num_timeouts = Session.check_task_timeouts()
        if num_timeouts > 0:
            logger.debug("timed out " + str(num_timeouts) + " tasks")
        
        #logger.debug("checking session timeouts")
        num_timeouts = Session.check_session_timeouts()
        if num_timeouts > 0:
            logger.debug("timed out " + str(num_timeouts) + " sessions")
        
        logger.debug("websock stats: " + str(websock_router.stats.dump()))

    def start_session_and_task_monitor(self):
        # start the session and task timeout monitor
        self.timer = tornado.ioloop.PeriodicCallback(Application.check_sess_and_task_timeouts, 1000*60*30)
        self.timer.start()
        
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
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s', '%m/%d/%Y %I.%M.%S.%p')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        tornado_access_logger.addHandler(handler)
        tornado_application_logger.addHandler(handler)
        tornado_general_logger.addHandler(handler)
    else:
        logging.basicConfig()

    logger.info('starting up...')
    logger.debug("listening on - " + SRVR_CFG.listen_ip + ':' + str(SRVR_CFG.port))
    logger.debug("hostname - " + SRVR_CFG.host)
    logger.debug("multiuser - " + str(SRVR_CFG.multiuser))
    logger.debug("headless - " + str(SRVR_CFG.headless))

    AsyncRunner.DEFAULT_REPLY = {'complete': True, 'success': False}
    if (Utils.temp_files_root != None):
        AsyncRunner.FILTER_STRINGS = [Utils.temp_files_root]
    AsyncRunner.LOG_MSG = WSMsg.SHOW_LOG

    app = Application()
    server = tornado.httpserver.HTTPServer(app)
    server.listen(SRVR_CFG.port, address=SRVR_CFG.listen_ip)
    if not SRVR_CFG.headless:
        webbrowser.open(SRVR_CFG.http_url)

    if SRVR_CFG.multiuser:
        # start the session and task timeout monitor
        app.start_session_and_task_monitor()    
    
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

