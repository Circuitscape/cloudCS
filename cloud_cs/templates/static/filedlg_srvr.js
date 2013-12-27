var file_dlg_result_target = '';
var file_dlg_cwd = '';
var file_dlg_type = '';

var file_dlg_headers = {
	'habitat_file_select': "Choose Habitat Map File",
	'habitat_mask_file_select': "Choose Habitat Mask File",
	'short_circuit_file_select': "Choose Short Circuit File",
	'focal_nodes_file_select': "Choose Focal Node File",
	'incl_excl_file_select': "Choose Include/Exclude Nodes File",
	'src_strength_file_select': "Choose Source Strengths File",
	'current_sources_file_select': "Choose Current Sources File",
	'ground_points_file_select': "Choose Ground Points File",
	'output_file_select': "Choose Output File",
	'menu_load_file_select': "Choose a Configuration File",
	'menu_batch_folder_select': "Choose Folder with Configuration Files"
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
	'output_file_select': '',
	'menu_load_file_select': '',
	'menu_batch_folder_select': 'folder'
};

function file_dlg_list(dir) {
	data = {};
	if(file_dlg_cwd.length > 0) {
		data['cwd'] = file_dlg_cwd;
	}
	if(dir) {
		data['dir'] = dir;
	}
	ws_conn.send(JSON.stringify({
		'msg_type': ws_msg_types.REQ_FILE_LIST,
		'data': data
	}));				
};

function file_dlg_populate(resp) {
	if (resp.msg_type == ws_msg_types.RSP_FILE_LIST) {
		file_dlg_cwd = resp.data.dir;
		$('#filedlg_div_dir').html(file_dlg_cwd);
		if(file_dlg_type == 'folder'){
			path_segments = file_dlg_cwd.split(/[\\\/]/);
			$('#filedlg_filename').val(path_segments[path_segments.length-1]);
		}
		files_html = "";
		for(idx=0; idx < resp.data.filelist.length; idx++) {
			filename = resp.data.filelist[idx][0];
			is_dir = resp.data.filelist[idx][1];
			if((file_dlg_type == 'folder') && !is_dir) continue;
			files_html += ("<li class=\"" + (is_dir ? "filedlg_dir" : "filedlg_file") + "\">" + filename + "</li>"); 
		}
		$('#filedlg_div_files').html(files_html);
		$('.filedlg_dir').click(function(e){
			dirname = $(this).html();
			if(file_dlg_type != 'folder') $('#filedlg_filename').val('');
			file_dlg_list(dirname);
		});
		$('.filedlg_file').click(function(e){
			sel_file = $(this).html();
			$('#filedlg_filename').val(sel_file);
		});
	}	
};

function file_dlg_init(target_id) {
	file_dlg_result_target = target_id.substring(0, target_id.lastIndexOf('_'));
	file_dlg_type = file_dlg_types[target_id];
	$('#'+file_dlg_result_target).val('');
	$('#filedlg_filename').val('');
	$('#filedlg_div_title').html(file_dlg_headers[target_id]);
	$('#filedlg_div').modal('show');

	do_ws(function(){
			file_dlg_list();
		},
		file_dlg_populate);
};

function file_dlg_on_select() {
	sel_file = file_dlg_cwd;
	if(file_dlg_type != 'folder') sel_file += ("/" + $('#filedlg_filename').val());
	$('#'+file_dlg_result_target).val(sel_file);
	$('#'+file_dlg_result_target).change();
};
