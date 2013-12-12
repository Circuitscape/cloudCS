var file_dlg_result_target = '';
var file_dlg_cwd = '';

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
	'menu_load_file_select': "Choose a Configuration File"
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
		files_html = "";
		for(idx=0; idx < resp.data.filelist.length; idx++) {
			filename = resp.data.filelist[idx][0];
			is_dir = resp.data.filelist[idx][1];
			files_html += ("<li class=\"" + (is_dir ? "filedlg_dir" : "filedlg_file") + "\">" + filename + "</li>"); 
		}
		$('#filedlg_div_files').html(files_html);
		$('.filedlg_dir').click(function(e){
			file_dlg_list($(this).html());
		});
		$('.filedlg_file').click(function(e){
			sel_file = $(this).html();
			$('#filedlg_filename').val(sel_file);
		});
	}	
};

function file_dlg_init(target_id) {
	file_dlg_result_target = target_id.substring(0, target_id.lastIndexOf('_'));
	$('#'+file_dlg_result_target).val('');
	$('#filedlg_filename').val('');
	$('#filedlg_div_title').html(file_dlg_headers[target_id]);
	$('#filedlg_div').modal('show');

	do_ws(function(){
			file_dlg_list();
		},
		file_dlg_populate);
};
