import hashlib, time, logging, tempfile, os

logger = logging.getLogger('cloudCS')

class Session:
    COOKIE_NAME = "cloudcs_sess"
    SALT = "" # this should be set from configuration on initialization
        
    def auth_valid(self, req):
        logger.info("authenticated " + self.user_id())
        self.local_work_dir = tempfile.mkdtemp()
        logger.debug("created temporary folder " + self.local_work_dir)
        req.set_secure_cookie(Session.COOKIE_NAME, self.sess_id, 1)
        req.redirect('/auth/storage')

    def remove_temporary_files(self):
        outdir = self.local_work_dir
        if None != outdir:
            for root, dirs, files in os.walk(outdir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(outdir)
        logger.debug("removed temporary folder " + outdir)

    @classmethod
    def work_dir(cls, sess_id):
        sess = cls.get_session(sess_id)
        return sess.local_work_dir
    
    @classmethod
    def storage_auth_valid(cls, req, credentials, store):
        sess_id = cls.extract_session_id(req)
        sess = cls.get_session(sess_id)
        sess.set('storage_creds', credentials)
        sess.set('store', store)
        req.redirect('/')

    @classmethod
    def validated_user_id(cls, req):
        return cls.get_session(cls.extract_session_id(req)).user_id()
    
    @classmethod
    def validated_user_name(cls, req):
        return cls.get_session(cls.extract_session_id(req)).user_name()
    
    @classmethod
    def extract_session_id(cls, req):
        return req.get_secure_cookie(Session.COOKIE_NAME)

    @classmethod
    def get_storage(cls, sess_id):
        sess = cls.get_session(sess_id)
        return (sess.get('storage_creds'), sess.get('store'))
    
    @classmethod
    def validate(cls, req):
        logger.debug("validating request")
        valid = False
        try:
            sess_id = cls.extract_session_id(req)
            valid = cls.validate_sess_id(sess_id)
        except Exception:
            logger.exception("Exception in validating")
        finally:
            if not valid:
                logger.debug("redirecting request for authentication")
                req.redirect('/auth/login')
                return False
            return True

    @classmethod
    def validate_sess_id(cls, sess_id):
        logger.debug('validating sess_id ' + sess_id)
        sess = cls.get_session(sess_id) if (sess_id != None) else None
        #logger.debug('sess = ' + str(sess) + " for sess_id " + sess_id)
        return (sess != None)



class SessionInMemory(Session):
    SESS_STORE = {}
    
    def __init__(self, user):
        self.user = user
        self.uid = user['email']
        self.creation_time = time.time()
        self.sess_id = hashlib.sha1('_'.join([self.uid, Session.SALT, str(self.creation_time)])).hexdigest()
        self.nv = {}
        SessionInMemory.SESS_STORE[self.sess_id] = self
        logger.debug("created session for " + self.uid + " with key " + self.sess_id)
    
    def user_id(self):
        return self.uid
    
    def user_name(self):
        return self.user['name']
    
    def set(self, attrib_name, attrib_val):
        self.nv[attrib_name] = attrib_val
    
    def get(self, attrib_name, default=None):
        return self.nv.get(attrib_name, default)

    @classmethod
    def is_valid(cls, sess_id):
        return (sess_id in SessionInMemory.SESS_STORE.keys())

    @classmethod
    def get_session(cls, sess_id):
        sess = None
        if SessionInMemory.is_valid(sess_id):
            sess = SessionInMemory.SESS_STORE[sess_id]
        else:
            logger.error("session id " + str(sess_id) + " not found")            
        return sess

    @classmethod
    def logout(cls, sess_id):
        if sess_id:
            logger.info("logging out " + str(sess_id))
            sess = SessionInMemory.SESS_STORE[sess_id]
            sess.remove_temporary_files() #TODO: make facility to allow offline processing even after user logs out
            del SessionInMemory.SESS_STORE[sess_id]

    @classmethod
    def logout_all(cls):
        for sess_id in SessionInMemory.SESS_STORE.keys():
            cls.logout(sess_id)
