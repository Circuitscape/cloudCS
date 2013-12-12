var file_dlg_result_target = '';
var file_dlg_cwd = '';
var google_developer_key = '';
var google_app_id = '';
var google_user = '';

var file_dlg_headers = {
	'habitat_file_select': "Choose Habitat Map File",
	'habitat_mask_file_select': "Choose Habitat Mask File",
	'short_circuit_file_select': "Choose Short Circuit File",
	'focal_nodes_file_select': "Choose Focal Node File",
	'incl_excl_file_select': "Choose Include/Exclude Nodes File",
	'src_strength_file_select': "Choose Source Strengths File",
	'current_sources_file_select': "Choose Current Sources File",
	'ground_points_file_select': "Choose Ground Points File",
	'output_file_select': "Choose Output Folder",
	'menu_load_file_select': "Choose a Configuration File"
};

var file_dlg_types = {
	'habitat_file_select': '',
	'habitat_mask_file_select': '',
	'short_circuit_file_select': '',
	'focal_nodes_file_select': '',
	'incl_excl_file_select': '',
	'src_strength_file_select': '',
	'current_sources_file_select': '',
	'ground_points_file_select': '',
	'output_file_select': 'application/vnd.google-apps.folder',
	'menu_load_file_select': ''
};

function file_dlg_populate(data) {
	if (data.action == google.picker.Action.PICKED) {
		var doc = data.docs[0];
		var file_id = doc.id;
        url = doc[google.picker.Document.URL];
        filename = doc[google.picker.Document.NAME];
        fullpath = "gdrive://" + filename + "/" + file_id;
        $('#'+file_dlg_result_target).val(fullpath);
        $('#'+file_dlg_result_target).change();
	}
};
      
function file_dlg_init(target_id) {
	file_dlg_result_target = target_id.substring(0, target_id.lastIndexOf('_'));
	$('#'+file_dlg_result_target).val('');
	
	var view = new google.picker.DocsView(google.picker.ViewId.FOLDERS);
      view.setMode(google.picker.DocsViewMode.LIST);
      if(file_dlg_types[target_id] == 'application/vnd.google-apps.folder') {
	      view.setSelectFolderEnabled(true);
	      view.setMimeTypes('application/vnd.google-apps.folder');      	
      }
      var picker = new google.picker.PickerBuilder()
          .enableFeature(google.picker.Feature.NAV_HIDDEN)
          .disableFeature(google.picker.Feature.MULTISELECT_ENABLED)
          .setAppId(google_app_id)
          .addView(view)
          //.addView(new google.picker.View(google.picker.ViewId.FOLDERS))
          .setAuthUser(google_user)
          .setDeveloperKey(google_developer_key)
          .setCallback(file_dlg_populate)
          .setSize(800,400)
          .setTitle(file_dlg_headers[target_id])
          .build();
       picker.setVisible(true);       
};

function file_dlg_init_api(devkey, appid, userhint) {
	google_developer_key = devkey;
	google_user = userhint;
	google_app_id = appid;
	gapi.load('picker');
};
