import sys, os, webbrowser, json, logging
from circuitscape.compute import Compute

import tornado.web
import tornado.websocket
import tornado.httpserver
import tornado.ioloop

class WSMsg:
    REQ_FILE_LIST = 1
    RSP_FILE_LIST = 2
    RSP_ERROR = -1
    def __init__(self, msg_type=None, msg_nv=None, msg=None):
        if msg:
            self.nv = json.loads(msg)
        else:
            self.nv = {
                       'msg_type': msg_type,
                       'data': msg_nv
            }
        print("got WSMsg msg_type: " + str(self.nv['msg_type']) + " type:" + str(type(self.nv['msg_type'])))
        print("got WSMsg data: " + str(self.nv['data']))

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
        pass

    def dump(self, obj):
        for attr in dir(obj):
            print "obj.%s = %s" % (attr, getattr(obj, attr))
    
    def on_message(self, message):
        #self.dump(message)
        print("message=[%s]"%(str(message),))
        wsmsg = WSMsg(msg=message)
        try:
            if (wsmsg.msg_type() == WSMsg.REQ_FILE_LIST):
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
                response = {'filelist': filelist, 'dir': curdir}
                
            wsmsg.reply(response, self)
        except Exception as e:
            logging.exception("Exception handling message of type %s"%(wsmsg.msg_type(),), e)
            wsmsg.error(-1, self)

    def on_close(self):
        pass


class IndexPageHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("cs.html")


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', IndexPageHandler),
            (r'/websocket', WebSocketHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': 'templates/static'}),
            (r'/ext/(.*)', tornado.web.StaticFileHandler, {'path': 'ext'})
        ]

        settings = {
            'template_path': 'templates',
            'debug': True
        }
        tornado.web.Application.__init__(self, handlers, **settings)


if __name__ == '__main__':
    ws_app = Application()
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(8080)
    #webbrowser.open('http://localhost:8080/') 
    tornado.ioloop.IOLoop.instance().start()
    