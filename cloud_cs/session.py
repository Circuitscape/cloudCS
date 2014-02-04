import hashlib, time, logging
from abc import ABCMeta, abstractmethod
from common import Utils

logger = logging.getLogger('cloudCS.session')

class Session:
    __metaclass__ = ABCMeta
    
    cookie_name = "cloudcs_sess"

    def auth_valid(self, req):
        logger.info("authenticated " + self.user_id())
        if not self.cfg().is_user_allowed(self.user_id()):
            raise RuntimeError("user not authorized")
        logger.debug("user " + self.user_id() + " allowed in role(s) " + str(self.user_role()))
        
        self.local_work_dir = None
        # reattach older session if available
        old_sessions = self.remove_older_sessions()
        self.task = None
        self.detach = False
        for sess in old_sessions:
            if sess.task == None:
                continue
            self.task = sess.task
            self.detach = True
            self.local_work_dir = sess.local_work_dir
            self.reattach_older_session(sess)
            break
        
        if None == self.local_work_dir:
            self.local_work_dir = Utils.mkdtemp(prefix="sess_")
            logger.debug("created temporary folder " + self.local_work_dir)
        else:
            logger.debug("reattached to old temporary folder " + self.local_work_dir)
        req.set_secure_cookie(Session.cookie_name, self.sess_id, 1)
        
        req.redirect('/auth/storage?uid=' + self.user_id())
            
    def remove_temporary_files(self):
        outdir = self.local_work_dir
        if None != outdir:
            Utils.rmdir(outdir)
            logger.debug("removed temporary folder " + outdir)

    @staticmethod
    def extract_session_id(req):
        return req.get_secure_cookie(Session.cookie_name)

    @abstractmethod
    def reattach_older_session(self, sess):
        pass

    @abstractmethod
    def remove_older_sessions(self):
        raise NotImplementedError
    
    @abstractmethod
    def cfg(self):
        raise NotImplementedError

    @abstractmethod
    def get_session(self, sess_id):
        raise NotImplementedError

    @abstractmethod
    def user_id(self):
        raise NotImplementedError
    
    @abstractmethod
    def user_name(self):
        raise NotImplementedError

    def is_user_in_role(self, role):
        userroles = self.cfg().get_user_role(self.user_id())
        checkroles = role if isinstance(role, list) else [role]
        for eachrole in checkroles:
            if eachrole in userroles:
                return True
        return False

    def user_role(self):
        return self.cfg().get_user_role(self.user_id())

    @abstractmethod
    def set(self, attrib_name, attrib_val):
        raise NotImplementedError
    
    @abstractmethod
    def get(self, attrib_name, default=None):
        raise NotImplementedError

    @abstractmethod
    def logout(self):
        raise NotImplementedError

    @abstractmethod
    def logout_all(self):
        raise NotImplementedError

    def work_dir(self):
        return self.local_work_dir
    
    def storage_auth_valid(self, req, credentials, store):
        self.set('storage_creds', credentials)
        self.set('store', store)
        req.redirect('/')

    def storage(self):
        return (self.get('storage_creds'), self.get('store'))

    @abstractmethod
    def check_session_timeouts(self):
        raise NotImplementedError
    
    @abstractmethod
    def check_task_timeouts(self):
        raise NotImplementedError

class SessionStandalone(Session):
    def __init__(self, user):
        self.user = self.uid = user
        self.creation_time = time.time()
        self.sess_id = 'standalone'
        self.nv = {}
        self.task = None
        self.detach = False
        logger.debug("created standalone session for " + self.uid + " with key " + self.sess_id)

    def user_id(self):
        return self.uid
    
    def user_name(self):
        return self.user
    
    def set(self, attrib_name, attrib_val):
        self.nv[attrib_name] = attrib_val
    
    def get(self, attrib_name, default=None):
        return self.nv.get(attrib_name, default)

    def reattach_older_session(self, sess):
        raise NotImplementedError

    def remove_older_sessions(self):
        raise NotImplementedError
    
    @staticmethod
    def cfg():
        return SessionInMemory.srvr_cfg

    def get_session(self, sess_id):
        raise NotImplementedError

    def logout(self):
        raise NotImplementedError

    def logout_all(self):
        raise NotImplementedError

    @staticmethod
    def check_session_timeouts():
        raise NotImplementedError

    @staticmethod
    def check_task_timeouts():
        raise NotImplementedError

class SessionInMemory(Session):
    SESS_STORE = {}
    srvr_cfg = None
    
    def __init__(self, user):
        self.user = user
        self.uid = user['email']
        self.creation_time = time.time()
        self.sess_id = hashlib.sha1('_'.join([self.uid, self.cfg().cfg_get("SECURE_SALT"), str(self.creation_time)])).hexdigest()
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

    @staticmethod
    def cfg():
        return SessionInMemory.srvr_cfg
    
    @staticmethod
    def _is_valid(sess_id):
        return (sess_id in SessionInMemory.SESS_STORE.keys())

    @staticmethod
    def get_session(sess_id):
        sess = None
        if SessionInMemory._is_valid(sess_id):
            sess = SessionInMemory.SESS_STORE[sess_id]
        else:
            logger.error("session id " + str(sess_id) + " not found")            
        return sess

    def logout(self):
        logger.info("logging out " + self.sess_id)
        self.remove_temporary_files()
        if self.sess_id in SessionInMemory.SESS_STORE.keys():
            del SessionInMemory.SESS_STORE[self.sess_id]

    def remove_older_sessions(self):
        logger.info("getting older sessions of " + self.sess_id + " id:" + self.uid)
        ret = []
        for sess_id in SessionInMemory.SESS_STORE.keys():
            sess = SessionInMemory.SESS_STORE[sess_id]
            if (sess.uid == self.uid) and (sess.sess_id != self.sess_id):
                logger.info("found old session " + sess.sess_id + " of user id:" + sess.uid)
                ret.append(sess)
                del SessionInMemory.SESS_STORE[sess_id]
        return ret

    def reattach_older_session(self, sess):
        self.creation_time = sess.creation_time

    @staticmethod
    def logout_all():
        for sess in SessionInMemory.SESS_STORE.values():
            sess.logout()

    @staticmethod
    def check_task_timeouts():
        num_timeouts = 0
        time_now = time.time()
        timeout_mins = SessionInMemory.cfg().cfg_get("timeout_execution", int, 300)
        logger.debug("timeout_execution:" + str(timeout_mins))
        for sess in SessionInMemory.SESS_STORE.values():
            if (not hasattr(sess, 'task')) or (None == sess.task):
                continue
            task = sess.task 
            age = int((time_now - task.creation_time)/60)
            logger.debug("task for session " + str(sess.sess_id) + " created at:" + str(task.creation_time) + " age:" + str(age))
            if age > timeout_mins:
                try:
                    num_timeouts += 1
                    try:
                        task.wslogger.send_error_msg("Task took too long. Timed out.")
                    except:
                        logger.error("error sending message. connection lost with client? session id " + str(sess.sess_id))
                    task.abort()
                except:
                    logger.error("error timing out task in sess id " + str(sess.sess_id))
        return num_timeouts

    @staticmethod
    def check_session_timeouts():
        num_timeouts = 0
        time_now = time.time()
        timeout_mins = SessionInMemory.cfg().cfg_get("timeout_session", int, 360)
        logger.debug("timeout_session:" + str(timeout_mins))
        for sess in SessionInMemory.SESS_STORE.values():
            age = int((time_now - sess.creation_time)/60)
            logger.debug("session " + str(sess.sess_id) + " created at:" + str(sess.creation_time) + " age:" + str(age))
            if age > timeout_mins:
                try:
                    num_timeouts += 1
                    if hasattr(sess, 'task') and (None != sess.task):
                        try:
                            sess.task.wslogger.send_error_msg("Session exceeded time slot. Timed out.")
                        except:
                            logger.error("error sending message. connection lost with client? session id " + str(sess.sess_id))
                        sess.task.abort()
                    sess.logout()
                except:
                    logger.error("error timing out session id " + str(sess.sess_id))
        return num_timeouts
