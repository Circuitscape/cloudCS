import traceback, tempfile, os, hashlib, pickle, zipfile

from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author

import tornado.web

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
