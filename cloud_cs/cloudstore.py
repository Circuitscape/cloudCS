import logging, httplib2, os, tempfile, codecs

import tornado.web
import tornado.gen

from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from oauth2client.client import OAuth2WebServerFlow

from common import PageHandlerBase
from session import SessionInMemory as Session

logger = logging.getLogger('cloudCS')

class CloudStore:
    
    def __init__(self, creds):
        pass
    
    def copy_to_local(self, file_path, local_path):
        pass

    def copy_to_remote(self, file_path, local_path):
        pass
    
    

class StorageHandlerBase(PageHandlerBase):
    def _on_auth(self, creds, store):
        if not creds:
            raise tornado.web.HTTPError(500, "Storage auth failed")
        logger.debug("storage authenticated for with credentials " + creds.to_json())
        Session.storage_auth_valid(self, creds, store)

    def get_error_html(self, status_code, **kwargs):
        return self.generic_get_error_html(status_code, message="Could not authenticate you to cloud storage.")

class GoogleDriveStore(CloudStore):
    def __init__(self, creds):
        http = httplib2.Http()
        self.http = creds.authorize(http)
        self.service = build('drive', 'v2', http=http)
    
    def all_to_local(self, workdir):
        pass
    
    @staticmethod
    def to_file_id(file_str):
        comps = file_str.split('/')
        return comps[len(comps)-1]
        
    def copy_to_local(self, file_id, local_path):
        logger.debug("got file_id " + str(file_id) + " of type " + str(type(file_id)))
        if file_id.startswith('gdrive://'):
            file_id = GoogleDriveStore.to_file_id(file_id)
             
        drive_file = self.service.files().get(fileId=file_id).execute()
        download_url = drive_file.get('downloadUrl')
        if not download_url:
            export_links = drive_file.get('exportLinks')
            if export_links:
                download_url = export_links.get('text/plain')
            
        if download_url:
            logger.debug("downdloading " + download_url) 
            resp, content = self.service._http.request(download_url)
            if resp.status == 200:
                logger.debug("downdload status " + str(resp.status) + " for " + download_url)
                if os.path.isdir(local_path):
                    local_file = tempfile.mktemp("_"+str(file_id), "gdrive_", dir=local_path)
                else:
                    local_file = local_path
                with open(local_file, 'w') as f:
                    if content.startswith(codecs.BOM_UTF8):
                        u = content.decode('utf-8-sig')
                        content = u.encode('utf-8')
                    f.write(content)
                    logger.debug("stored " + download_url + " to " + local_file)
                return local_file
            else:
                logger.error('Error downloading file: %s' % (str(resp),))
                return None
        else:
            logger.error('File empty or not found: %s' % (str(file_id),))
            return None        
    
    def copy_to_remote(self, folder_id, local_path):
        try:
            if folder_id.startswith('gdrive://'):
                folder_id = GoogleDriveStore.to_file_id(folder_id)

            media_body = MediaFileUpload(local_path, mimetype='text/plain', resumable=True)
            _local_dir, local_name = os.path.split(local_path)
            body = {
                    'title': local_name,
                    'description': local_name,
                    'mimeType': 'text/plain',
                    'parents': [{'id': folder_id}]
            }
            uploaded_file = self.service.files().insert(body=body, media_body=media_body).execute()
            logger.debug("uploaded local file " + local_path + " to gdrive file " + str(uploaded_file))
            return uploaded_file['id']
        except:
            logger.exception("error uploading local file " + local_path + " to gdrive")
            return None

class GoogleDriveHandler(StorageHandlerBase):
    OAUTH_SCOPE = 'https://www.googleapis.com/auth/drive'
    CLIENT_ID = ''
    CLIENT_SECRET = ''
    REDIRECT_URI = ''
    
    FLOW_STORE = {}

    @staticmethod
    def init(cfg):
        GoogleDriveHandler.CLIENT_ID = cfg.get("cloudCS", "GOOGLE_CLIENT_ID")
        GoogleDriveHandler.CLIENT_SECRET = cfg.get("cloudCS", "GOOGLE_CLIENT_SECRET")
        GoogleDriveHandler.REDIRECT_URI = cfg.get("cloudCS", "GOOGLE_STORAGE_AUTH_REDIRECT_URI")
        logger.debug("initialized CLIENT_ID=" + GoogleDriveHandler.CLIENT_ID)
        logger.debug("initialized CLIENT_SECRET=" + GoogleDriveHandler.CLIENT_SECRET)
        logger.debug("initialized REDIRECT_URI=" + GoogleDriveHandler.REDIRECT_URI)
    
    @tornado.web.asynchronous
    @tornado.gen.engine
    def get(self):
        logger.debug("google drive auth invoked")
        flow_id = self.get_argument("state", None)
        if (None != flow_id):
            credentials = yield tornado.gen.Task(self._get_credentials, flow_id)
            self._on_auth(credentials, GoogleDriveStore(credentials))
        else:
            self._get_code()
    
    def _get_code(self):
        flow = OAuth2WebServerFlow(GoogleDriveHandler.CLIENT_ID, GoogleDriveHandler.CLIENT_SECRET, 
                                   GoogleDriveHandler.OAUTH_SCOPE, GoogleDriveHandler.REDIRECT_URI,
                                   approval_prompt="force")
        flow_id = str(id(flow))
        flow.params.update({'state':flow_id})
        
        GoogleDriveHandler.FLOW_STORE[flow_id] = flow
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
        
