import traceback, tempfile, os, hashlib, pickle, zipfile, json, logging, signal
from multiprocessing import Process, Queue
from abc import ABCMeta, abstractmethod

import tornado.web, tornado.ioloop

from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author

class PageHandlerBase(tornado.web.RequestHandler):
    def generic_get_error_html(self, status_code, **kwargs):
        kwargs.update({
                  'version': cs_version,
                  'author': cs_author,                  
                  'status_code': status_code,
        })
        
        if self.settings.get("debug") and "exc_info" in kwargs:
            exc_info = kwargs["exc_info"]
            trace_info = ''.join(["%s<br/>" % line for line in traceback.format_exception(*exc_info)])
            request_info = ''.join(["<strong>%s</strong>: %s<br/>" % (k, self.request.__dict__[k] ) for k in self.request.__dict__.keys()])
            error = exc_info[1]
            
            kwargs['message'] = "<br/><br/>".join([kwargs['message'], "Error: " + error, "Request Info: " + request_info, "Trace: " + trace_info])
            
        return self.render_string("cs_error.html", **kwargs)


class ErrorHandler(tornado.web.ErrorHandler, PageHandlerBase): 
    def prepare(self): 
        raise tornado.web.HTTPError(self._status_code) 


class Utils:
    temp_files_root = None
    
    @staticmethod
    def mkdtemp(suffix="", prefix=""):
        return tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=Utils.temp_files_root)

    @staticmethod
    def rmdir(dir_path, contents_only=False):
        if (None == dir_path) or (not os.path.exists(dir_path)):
            return
       
        for root, dirs, files in os.walk(dir_path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
                
        if not contents_only:
            os.rmdir(dir_path)

    @staticmethod
    def hash(*args):
        return hashlib.sha1('_'.join(args)).hexdigest()
    
    #TODO: handle revoke conditions
    @staticmethod
    def stash_storage_creds(sec_salt, uid, creds):
        uid_hash = Utils.hash(uid, sec_salt)
        # TODO: encrypt contents
        filename = os.path.join(Utils.creds_store_path(), uid_hash)
        with open(filename, 'wb') as f:
            pickle.dump(creds, f)
    
    @staticmethod
    def retrieve_storage_creds(sec_salt, uid):
        uid_hash = Utils.hash(uid, sec_salt)
        # TODO: encrypt contents
        filename = os.path.join(Utils.creds_store_path(), uid_hash)
        result = None
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                result = pickle.load(f)
        return result
    
    @staticmethod
    def creds_store_path():
        creds_path = os.path.join(Utils.temp_files_root, 'creds')
        if not os.path.exists(creds_path):
            os.mkdir(creds_path)
        return creds_path 


    @staticmethod
    def compress_folder(directory, zipfilename):
        zipf = zipfile.ZipFile(zipfilename, "w", compression=zipfile.ZIP_DEFLATED)
        Utils.recursive_zip(zipf, directory)
        zipf.close()


    @staticmethod
    def recursive_zip(zipf, directory, folder = ""):
        for item in os.listdir(directory):
            if os.path.isfile(os.path.join(directory, item)):
                zipf.write(os.path.join(directory, item), folder + os.sep + item)
            elif os.path.isdir(os.path.join(directory, item)):
                Utils.recursive_zip(zipf, os.path.join(directory, item), folder + os.sep + item)

class BaseMsg:
    RSP_ERROR = -1
    SHOW_LOG = 0
    
    logger = None
        
    def __init__(self, msg_type=None, msg_nv=None, msg=None, handler=None):
        self.handler = handler
        if msg:
            self.nv = json.loads(msg)
        else:
            self.nv = {
                       'msg_type': msg_type,
                       'data': msg_nv
            }
        BaseMsg.logger.debug('received msg_type: %d, data[%s]' % (self.nv['msg_type'], str(self.nv['data'])))

    def msg_type(self):
        return self.nv['msg_type']

    def data_keys(self):
        return self.nv['data'].keys()

    def data(self, key, default=None):
        return self.nv['data'].get(key, default);

    def error(self, err_code, sock=None):
        resp_nv = {
                   'msg_type': BaseMsg.RSP_ERROR,
                   'data': err_code
        }
        if sock == None:
            sock = self.handler
        sock.write_message(resp_nv, False)

    def reply(self, response, sock=None):
        resp_nv = {
                   'msg_type': (self.nv['msg_type'] + 1),
                   'data': response
        }
        if sock == None:
            sock = self.handler
        sock.write_message(resp_nv, False)

    def reply_async(self, response):
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.add_callback(lambda x: x[0].reply(x[1]), (self, response))

    def error_async(self, err_code):
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.add_callback(lambda x: x[0].error(x[1]), (self, err_code))


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

    def send_error_msg(self, msg):
        resp_nv = {
                   'msg_type': BaseMsg.RSP_ERROR,
                   'data': msg
        }
        self.dest.write_message(resp_nv, False)

    def send_log_msg(self, msg):
        resp_nv = {
                   'msg_type': BaseMsg.SHOW_LOG,
                   'data': msg
        }
        self.dest.write_message(resp_nv, False)
    
    def send_log_msg_async(self, msg):
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.add_callback_from_signal(lambda x: x[0].send_log_msg(x[1]), (self, msg))



class QueueLogger(logging.Handler):
    def __init__(self, q):
        logging.Handler.__init__(self)
        self.q = q
        self.level = logging.DEBUG

    def flush(self):
        pass

    def emit(self, record):
        msg = self.format(record)
        msg = msg.strip('\r')
        msg = msg.strip('\n')
        self.send_log_msg(msg)

    def send_log_msg(self, msg):
        self.q.put((BaseMsg.SHOW_LOG, msg))
    
    def send_result_msg(self, msg_type, ret):
        self.q.put((msg_type, ret))

    def send_error_msg(self, msg):
        self.q.put((BaseMsg.RSP_ERROR, msg))

class AsyncRunner(object):
    __metaclass__ = ABCMeta
    
    DEFAULT_REPLY = None
    
    def __init__(self, wslogger, wsmsg, method, *args):
        q = Queue()
        in_msg_type = wsmsg.msg_type()
        
        args = list(args)
        args.insert(0, in_msg_type)
        args.insert(0, QueueLogger(q))

        self.results = None
        self.p = Process(target=method, args=args)
        self.q = q
        self.in_msg_type = in_msg_type
        self.wslogger = wslogger
        self.wsmsg = wsmsg
        self.p.start()        
        self._start_handler(q)
            
    def _start_handler(self, q):
        if hasattr(q, '_reader'):
            # use the reader fd to hook into ioloop
            self.fd = q._reader.fileno()
            ioloop = tornado.ioloop.IOLoop.instance()
            ioloop.add_handler(self.fd, lambda fd, events: self._process_q(), tornado.ioloop.IOLoop.READ | tornado.ioloop.IOLoop.ERROR)
        else:
            self.timer = tornado.ioloop.PeriodicCallback(lambda: self._process_q(), 1000)
            self.timer.start()

    def _stop_handler(self):
        if hasattr(self, 'timer'):
            if self.timer != None:
                self.timer.stop()
                self.timer = None
        elif hasattr(self, 'fd'):
            if self.fd != None:
                ioloop = tornado.ioloop.IOLoop.instance()
                ioloop.remove_handler(self.fd)
                self.fd = None

    def abort(self):
        self.wslogger.send_log_msg("Aborting...")
        self._stop_handler()
        if None != self.p:
            self.wslogger.send_log_msg("Sending terminate request...")
            self.p.terminate()
            self.p.join(timeout=5)
            if self.p.is_alive():
                self.wslogger.send_log_msg("Sending kill signal...")
                os.kill(self.p.pid, signal.SIGKILL)
                self.p.join(timeout=5)
                if self.p.is_alive():
                    self.wslogger.send_log_msg("Could not terminate. Abandoning.")
            self.p = None

        self.wslogger.send_log_msg("Aborted.")
        self.wsmsg.reply(AsyncRunner.DEFAULT_REPLY)
        self.completed()

    @abstractmethod
    def completed(self):
        raise NotImplementedError

    def _process_q(self):
        try:
            while (self.results == None) or self.p.is_alive() or (not self.q.empty()):
                msg_type, msg = self.q.get(False)
                if msg_type == BaseMsg.SHOW_LOG:
                    self.wslogger.send_log_msg(msg)
                if msg_type == BaseMsg.RSP_ERROR:
                    self.wslogger.send_error_msg(msg)
                elif msg_type == self.in_msg_type:
                    self.results = msg
        except:
            pass
        
        if (self.results != None) or ((not self.p.is_alive()) and self.q.empty()):
            self._stop_handler()
            self.p.join()
            self.p = None
            if self.results:
                self.wsmsg.reply(self.results)
            elif None != AsyncRunner.DEFAULT_REPLY:
                # send a failure message if process died without responding
                self.wsmsg.reply(AsyncRunner.DEFAULT_REPLY)
            self.completed()

    