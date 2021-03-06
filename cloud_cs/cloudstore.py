import logging, httplib2, os, tempfile, codecs, tornado, time
from abc import ABCMeta, abstractmethod

from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from oauth2client.client import OAuth2WebServerFlow

from common import PageHandlerBase, Utils
from session import SessionInMemory as Session

logger = logging.getLogger('cloudCS.store')

class CloudStore:
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def __init__(self, creds, log_str):
        raise NotImplementedError
    
    @abstractmethod
    def to_file_name(self, file_path):
        raise NotImplementedError
    
    @abstractmethod
    def copy_to_local(self, file_path, local_path):
        raise NotImplementedError

    @abstractmethod
    def copy_to_remote(self, file_path, local_path):
        raise NotImplementedError
    
    

class StorageHandlerBase(PageHandlerBase):
    SEC_SALT = ''
    
    def _get_stashed_creds(self):
        uid = self.get_argument("uid", None)
        credentials = None
        if uid != None:
            # try to retrieve storage authorization from database
            credentials = Utils.retrieve_storage_creds(StorageHandlerBase.SEC_SALT, uid)
        if None != credentials:
            logger.debug("[%s] retrieved stashed credentials", str(uid))
        return (uid, credentials)
        
    def _on_auth(self, uid, creds, store):
        if not creds:
            raise tornado.web.HTTPError(500, "Storage auth failed")
        sess_id = Session.extract_session_id(self)
        sess = Session.get_session(sess_id)
        logger.debug("%s storage authenticated for with credentials %s", sess.log_str(), creds.to_json())
        sess.storage_auth_valid(self, creds, store)
        if uid != None:
            logger.debug("%s stashed credentials for %s", sess.log_str(), str(uid))
            Utils.stash_storage_creds(StorageHandlerBase.SEC_SALT, uid, creds)

    def get_error_html(self, status_code, **kwargs):
        return self.generic_get_error_html(status_code, message="Could not authenticate you to cloud storage.")


class GoogleDriveStore(CloudStore):
    def __init__(self, creds, log_str=''):
        http = httplib2.Http()
        self.http = creds.authorize(http)
        self.log_str = log_str
        self.service = build('drive', 'v2', http=http)
    
    def all_to_local(self, workdir):
        pass
    
    @staticmethod
    def to_file_id(file_str):
        comps = file_str.split('/')
        return comps[len(comps)-1]

    def to_file_name(self, file_str):
        comps = file_str.split('/')
        return comps[len(comps)-2]

    def copy_to_local(self, file_id, local_path, attempts=3):
        ex = None
        for attempt in range(1, attempts):
            try:
                return self._copy_to_local(file_id, local_path)
            except Exception as e:
                ex = e
                logger.warning("%s error downloading file: %s. attempt %d of %d", self.log_str, str(ex), attempt, attempts)
                if attempt < (attempts-1):
                    time.sleep(5*attempt)
        raise ex

                
    def _copy_to_local(self, file_id, local_path):
        logger.debug("%s got file_id %s of type %s", self.log_str, str(file_id), str(type(file_id)))
        if file_id.startswith('gdrive://'):
            file_id = GoogleDriveStore.to_file_id(file_id)
             
        drive_file = self.service.files().get(fileId=file_id).execute()
        download_url = drive_file.get('downloadUrl')
        mime_type = drive_file.get('mimeType')
        logger.debug("%s file mime type: %s", self.log_str, mime_type)
        if not download_url:
            logger.debug("%s looking for exportLinks as downloadUrl was not found", self.log_str)
            export_links = drive_file.get('exportLinks')
            if export_links:
                download_url = export_links.get('text/plain')
        
        if download_url:
            logger.debug("%s downloading %s", self.log_str, download_url) 
            resp, content = self.service._http.request(download_url)
            if resp.status == 200:
                logger.debug("%s downdload status %s for %s", self.log_str, str(resp.status), download_url)
                
                file_is_binary = (mime_type in ['application/x-gzip', 'application/zip'])
                file_open_mode = 'wb' if file_is_binary else 'w'
                file_extn = ''
                if (mime_type ==  'application/x-gzip'):
                    file_extn = '.gz'
                elif (mime_type ==  'application/zip'):
                    file_extn = '.zip'

                if os.path.isdir(local_path):
                    local_file = tempfile.mktemp("_"+str(file_id)+file_extn, "gdrive_", dir=local_path)
                else:
                    local_file = local_path
                
                logger.debug("%s file is binary: %s, file_open_mode: %s", self.log_str, str(file_is_binary), file_open_mode)
                with open(local_file, file_open_mode) as f:
                    if not file_is_binary:
                        if content.startswith(codecs.BOM_UTF8):
                            u = content.decode('utf-8-sig')
                            content = u.encode('utf-8')
                    f.write(content)
                    logger.debug("%s stored %s to %s", self.log_str, download_url, local_file)
                return local_file
            else:
                logger.error("%s Error downloading file: %s", self.log_str, str(resp))
                return None
        else:
            logger.error("%s File empty or not found: %s", self.log_str, str(file_id))
            return None        
    
    def copy_to_remote(self, folder_id, local_path, mime_type='text/plain', extract_folder_id=False):
        try:
            if folder_id.startswith('gdrive://'):
                folder_id = GoogleDriveStore.to_file_id(folder_id)
                if extract_folder_id:
                    folder_template_file = self.service.files().get(fileId=folder_id).execute()
                    parents = folder_template_file.get('parents')
                else:
                    parents = [{'id': folder_id}]
            elif isinstance(folder_id, list):
                parents = folder_id
            else:
                parents = [{'id': folder_id}]

            media_body = MediaFileUpload(local_path, mimetype='text/plain', resumable=True)
            _local_dir, local_name = os.path.split(local_path)
            body = {
                    'title': local_name,
                    'description': local_name,
                    'mimeType': mime_type,
                    'parents': parents
            }
            uploaded_file = self.service.files().insert(body=body, media_body=media_body).execute()
            logger.debug("%s uploaded local file %s to gdrive file %s", self.log_str, local_path, str(uploaded_file))
            return uploaded_file['id']
        except:
            logger.exception("%s error uploading local file %s to gdrive", self.log_str, local_path)
            return None


class GoogleDriveHandler(StorageHandlerBase):
    OAUTH_SCOPE = 'https://www.googleapis.com/auth/drive'
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    REDIRECT_URI = ''
    
    FLOW_STORE = {}

    @staticmethod
    def init(cfg):
        GoogleDriveHandler.CLIENT_ID = cfg.cfg_get("GOOGLE_CLIENT_ID")
        GoogleDriveHandler.CLIENT_SECRET = cfg.cfg_get("GOOGLE_CLIENT_SECRET")
        GoogleDriveHandler.REDIRECT_URI = cfg.cfg_get("GOOGLE_STORAGE_AUTH_REDIRECT_URI")
        StorageHandlerBase.SEC_SALT = cfg.cfg_get("SECURE_SALT")
        logger.debug("initialized CLIENT_ID=" + GoogleDriveHandler.CLIENT_ID)
        logger.debug("initialized CLIENT_SECRET=" + GoogleDriveHandler.CLIENT_SECRET)
        logger.debug("initialized REDIRECT_URI=" + GoogleDriveHandler.REDIRECT_URI)
    
    @tornado.web.asynchronous
    @tornado.gen.engine
    def get(self):
        logger.debug("google drive auth invoked")
        uid, credentials = self._get_stashed_creds()
        if credentials != None:
            self._on_auth(None, credentials, GoogleDriveStore(credentials, str(uid)))
            return
                    
        flow_id = self.get_argument("state", None)
        if (None != flow_id):
            credentials = yield tornado.gen.Task(self._get_credentials, flow_id)
            self._on_auth(flow_id, credentials, GoogleDriveStore(credentials, str(uid)))
        else:
            self._get_code(uid)
    
    def _get_code(self, uid):
        flow = OAuth2WebServerFlow(GoogleDriveHandler.CLIENT_ID, GoogleDriveHandler.CLIENT_SECRET, 
                                   GoogleDriveHandler.OAUTH_SCOPE, GoogleDriveHandler.REDIRECT_URI,
                                   approval_prompt="force")
        flow.params.update({'state':uid})
        
        GoogleDriveHandler.FLOW_STORE[uid] = flow
        authorize_url = flow.step1_get_authorize_url()
        self.redirect(authorize_url)
    
    def _get_credentials(self, flow_id, callback=None):
        #logger.debug("got google response for " + flow_id)
        code = self.get_argument("code", None)
        #logger.debug("got google authorization code=" + str(code))
        credentials = None
        flow = GoogleDriveHandler.FLOW_STORE[flow_id]
        del GoogleDriveHandler.FLOW_STORE[flow_id]
        if None != code:
            credentials = flow.step2_exchange(code)
        if None != callback:
            callback(credentials)
        
