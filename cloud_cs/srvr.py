import sys, os, webbrowser, json, logging, getpass, tempfile, StringIO
from circuitscape.compute import Compute
from circuitscape.cfg import CSConfig
from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author
from circuitscape import __file__ as cs_pkg_file

import tornado.web
import tornado.websocket
import tornado.httpserver
import tornado.ioloop

from cloudauth import GoogleHandler as AuthHandler
from cloudauth import SessionInMemory as Session

MULTIUSER = True

SERVER_HOST = "localhost"
SERVER_PORT = 8080
SERVER_WS_PATH = r'/websocket'
SERVER_WS_URL = "ws://" + SERVER_HOST + ':' + str(SERVER_PORT) + SERVER_WS_PATH

logging.basicConfig()
logger = logging.getLogger('cloudCS')
logger.setLevel(logging.DEBUG)
    

class WebSocketLogger(logging.Handler):
    def __init__(self, dest=None):
        logging.Handler.__init__(self)
        self.dest = dest
        self.level = logging.DEBUG

    def flush(self):
        pass

    def emit(self, record):
        msg = self.format(record)
        msg = msg.strip('\r')
        msg = msg.strip('\n')
        self.send_log_msg(msg)

    def send_log_msg(self, msg):
        resp_nv = {
                   'msg_type': WSMsg.SHOW_LOG,
                   'data': msg
        }
        self.dest.write_message(resp_nv, False)
        

class WSMsg:
    RSP_ERROR = -1
    SHOW_LOG = 0
    
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
    
    
    def __init__(self, msg_type=None, msg_nv=None, msg=None):
        if msg:
            self.nv = json.loads(msg)
        else:
            self.nv = {
                       'msg_type': msg_type,
                       'data': msg_nv
            }
        logger.debug('received msg_type: %d, data[%s]' % (self.nv['msg_type'], str(self.nv['data'])))

    def msg_type(self):
        return self.nv['msg_type']

    def data_keys(self):
        return self.nv['data'].keys()

    def data(self, key, default=None):
        return self.nv['data'].get(key, default);

    def error(self, err_code, sock):
        resp_nv = {
                   'msg_type': WSMsg.RSP_ERROR,
                   'data': err_code
        }
        sock.write_message(resp_nv, False)

    def reply(self, response, sock):
        resp_nv = {
                   'msg_type': (self.nv['msg_type'] + 1),
                   'data': response
        }
        sock.write_message(resp_nv, False)


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
        global MULTIUSER
        logger.debug("websocket message received [%s]"%(str(message),))
        wsmsg = WSMsg(msg=message)
        is_shutdown_msg = False
        response = {}
        try:
            if MULTIUSER and not self.is_authenticated:
                response, is_shutdown_msg = self.handle_auth(wsmsg)
            else:            
                if (wsmsg.msg_type() == WSMsg.REQ_FILE_LIST):
                    response, is_shutdown_msg = self.handle_file_list(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_LOGOUT):
                    response, is_shutdown_msg = self.handle_logout(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_RUN_VERIFY):
                    response, is_shutdown_msg = self.handle_run_verify(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_RUN_JOB):
                    response, is_shutdown_msg = self.handle_run_job(wsmsg)
                elif (wsmsg.msg_type() == WSMsg.REQ_LOAD_CFG):
                    response, is_shutdown_msg = self.handle_load_config(wsmsg)
                
            wsmsg.reply(response, self)
        except Exception:
            logger.exception("Exception handling message of type %d"%(wsmsg.msg_type(),))
            wsmsg.error(-1, self)
            
        if is_shutdown_msg:
            if MULTIUSER:
                Session.logout(wsmsg.data('sess_id'))
            else:
                stop_webserver()

#     def auth(self, wsmsg):
#         if (not self.is_authenticated) and (wsmsg.msg_type() == WSMsg.REQ_AUTH):
#             sess_id = wsmsg.data('sess_id')
#             self.is_authenticated = Session.validate_sess_id(sess_id)
#         return self.is_authenticated

    def handle_auth(self, wsmsg):
        if (not self.is_authenticated) and (wsmsg.msg_type() == WSMsg.REQ_AUTH):
            sess_id = wsmsg.data('sess_id')
            self.is_authenticated = Session.validate_sess_id(sess_id)
            return ({'success': self.is_authenticated}, not self.is_authenticated)
        return (None, not self.is_authenticated)
        

    def handle_load_config(self, wsmsg):
        result = None
        success = False
        try:
            filepath = wsmsg.data('filename')
            filedir, _filename = os.path.split(filepath)
            cfg = CSConfig(filepath)
            result = cfg.as_dict(rel_to_abs=filedir)
            success = True
        except Exception as e:
            logger.exception("Error reading configuration from %s"%(wsmsg.data('filename'),))
            result = str(e)
        logger.debug("returning config [" + str(result) + "]")
        return ({'cfg': result, 'success': success}, False)

    def handle_run_job(self, wsmsg):
        solver_failed = True
        
        cfg = CSConfig()
        for key in wsmsg.data_keys():
            cfg.__setattr__(key, wsmsg.data(key))
        (all_options_entered, message) = cfg.check()
        if not all_options_entered:
            wsmsg.error(message, self)
        else:
            # TODO: In cloud mode, this would be a temporary directory
            outdir, _out_file = os.path.split(cfg.output_file)
            
            try:
                configFile = os.path.join(outdir, 'circuitscape.ini')
                cfg.write(configFile)
    
                wslogger = WebSocketLogger(self)
                cs = Compute(configFile, wslogger)
                result, solver_failed = cs.compute()
                wslogger.send_log_msg("result: \n" + str(result))
            except Exception as e:
                message = str(e)
                wsmsg.error(message, self)

        success = not solver_failed
        return ({'complete': True, 'success': success}, False)
            
        

    def handle_run_verify(self, wsmsg):
        outdir = None
        cwd = os.getcwd()
        strio = StringIO.StringIO()
        try:
            root_path = os.path.dirname(cs_pkg_file)
            outdir = tempfile.mkdtemp()
            if os.path.exists(root_path):
                root_path = os.path.split(root_path)[0]
                os.chdir(root_path)     # otherwise we are running inside a packaged folder and resources are availale at cwd
            wslogger = WebSocketLogger(self)
            from circuitscape.verify import cs_verifyall
            testResult = cs_verifyall(out_path=outdir, ext_logger=wslogger, stream=strio)
            testsPassed = testResult.wasSuccessful()
        except:
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

        wslogger.send_log_msg(strio.getvalue())
        strio.close()
                
        return ({'complete': True, 'success': testsPassed}, False)
    
    def handle_logout(self, wsmsg):
        logger.debug("logging out")
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

class IndexPageHandler(tornado.web.RequestHandler):
    def get(self):
        global MULTIUSER
        if MULTIUSER:
            if not Session.validate(self):
                return
            username = Session.validated_user_name(self);
            txt_shutdown = "Logout"
            txt_shutdown_msg = "Are you sure you want to logout from Circuitscape?"
            sess_id = Session.extract_session_id(self)
        else:
            username = getpass.getuser()
            txt_shutdown = "Shutdown"
            txt_shutdown_msg = "Are you sure you want to close Circuitscape?"
            sess_id = ''
        
        kwargs = {
                  'username': username,
                  'version': cs_version,
                  'author': cs_author,
                  'ws_url': SERVER_WS_URL,
                  'sess_id': sess_id,
                  'txt_shutdown': txt_shutdown,
                  'txt_shutdown_msg': txt_shutdown_msg
        }
        self.render("cs.html", **kwargs)


class Application(tornado.web.Application):
    def __init__(self):
        pkgpath, _fname = os.path.split(__file__)
        templates_path = os.path.join(pkgpath, 'templates')
        static_path = os.path.join(pkgpath, 'templates/static')
        ext_path = os.path.join(pkgpath, 'ext')
        handlers = [
            (r'/', IndexPageHandler),
            (SERVER_WS_PATH, WebSocketHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': static_path}),
            (r'/ext/(.*)', tornado.web.StaticFileHandler, {'path': ext_path})
        ]
        
        if MULTIUSER:
            handlers.append((r'/auth', AuthHandler))

        settings = {
            'template_path': templates_path,
            'debug': True,
            "cookie_secret": Session.SALT,
        }
        tornado.web.Application.__init__(self, handlers, **settings)

def stop_webserver():
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.add_callback(lambda x: x.stop(), ioloop)

def run_webgui(port=SERVER_PORT, start_browser=True, multiuser=True):
    logger.debug('starting up...')
    global SERVER_WS_URL, SERVER_PORT, MULTIUSER
    if port:
        SERVER_PORT = port
    MULTIUSER = multiuser
    
    server = tornado.httpserver.HTTPServer(Application())
    server.listen(SERVER_PORT)
    SERVER_WS_URL = "ws://" + SERVER_HOST + ':' + str(SERVER_PORT) + SERVER_WS_PATH
    if start_browser:
        webbrowser.open('http://localhost:' + str(SERVER_PORT) + '/')
    tornado.ioloop.IOLoop.instance().start()
