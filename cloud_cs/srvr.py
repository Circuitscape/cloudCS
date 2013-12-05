import sys, os, webbrowser, json, logging, getpass, tempfile
from circuitscape.compute import Compute
from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author
from circuitscape import __file__ as cs_pkg_file

import tornado.web
import tornado.websocket
import tornado.httpserver
import tornado.ioloop

SERVER_HOST = "localhost"
SERVER_PORT = 8080
SERVER_WS_PATH = r'/websocket'
SERVER_WS_URL = "ws://" + SERVER_HOST + ':' + str(SERVER_PORT) + SERVER_WS_PATH

logging.basicConfig()
logger = logging.getLogger('cloudCS')
logger.setLevel(logging.DEBUG)

def stop_webserver():
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.add_callback(lambda x: x.stop(), ioloop)

def run_webserver(ws_app, port, start_browser):
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(port)
    if start_browser:
        webbrowser.open('http://localhost:' + str(port) + '/')
    tornado.ioloop.IOLoop.instance().start()
    

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
        resp_nv = {
                   'msg_type': WSMsg.SHOW_LOG,
                   'data': msg
        }
        self.dest.write_message(resp_nv, False)
        

class WSMsg:
    RSP_ERROR = -1
    SHOW_LOG = 0
    
    REQ_FILE_LIST = 1
    RSP_FILE_LIST = 2
    
    REQ_LOGOUT = 3
    RSP_LOGOUT = 4
    
    REQ_RUN_VERIFY = 5
    RSP_RUN_VERIFY = 6
    
    
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
        logger.debug("websocket connection opened")
            
    def on_close(self):
        logger.debug("websocket connection closed")

#     def dump(self, obj):
#         for attr in dir(obj):
#             print "obj.%s = %s" % (attr, getattr(obj, attr))
    
    def on_message(self, message):
        #self.dump(message)
        logger.debug("websocket message received [%s]"%(str(message),))
        wsmsg = WSMsg(msg=message)
        is_shutdown_msg = False
        response = {}
        try:
            if (wsmsg.msg_type() == WSMsg.REQ_FILE_LIST):
                response, is_shutdown_msg = self.handle_file_list(wsmsg)
            elif (wsmsg.msg_type() == WSMsg.REQ_LOGOUT):
                response, is_shutdown_msg = self.handle_logout(wsmsg)
            elif (wsmsg.msg_type() == WSMsg.REQ_RUN_VERIFY):
                response, is_shutdown_msg = self.handle_run_verify(wsmsg)
                
            wsmsg.reply(response, self)
        except Exception as e:
            logger.exception("Exception handling message of type %s"%(wsmsg.msg_type(),), e)
            wsmsg.error(-1, self)
            
        if is_shutdown_msg:
            stop_webserver()

    def handle_run_verify(self, wsmsg):
        outdir = None
        cwd = os.getcwd()
        try:
            root_path = os.path.dirname(cs_pkg_file)
            outdir = tempfile.mkdtemp()
            if os.path.exists(root_path):
                root_path = os.path.split(root_path)[0]
                os.chdir(root_path)     # otherwise we are running inside a packaged folder and resources are availale at cwd
            wslogger = WebSocketLogger(self)
            from circuitscape.verify import cs_verifyall
            testResult = cs_verifyall(out_path=outdir, ext_logger=wslogger)
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
                
        return ({'complete': True, 'success': testsPassed}, False)
    
    def handle_logout(self, wsmsg):
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
        kwargs = {
                  'username': getpass.getuser(),
                  'version': cs_version,
                  'author': cs_author,
                  'ws_url': SERVER_WS_URL,
        }
        self.render("cs.html", **kwargs)


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', IndexPageHandler),
            (SERVER_WS_PATH, WebSocketHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': 'templates/static'}),
            (r'/ext/(.*)', tornado.web.StaticFileHandler, {'path': 'ext'})
        ]

        settings = {
            'template_path': 'templates',
            'debug': True
        }
        tornado.web.Application.__init__(self, handlers, **settings)


if __name__ == '__main__':
    logger.debug('starting up...')
    run_webserver(Application(), SERVER_PORT, False)


