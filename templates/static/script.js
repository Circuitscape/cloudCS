var cs_ws_url = '';

function do_ws(onopen, onmessage) {
	ws_conn = new WebSocket(cs_ws_url);
	ws_conn.onopen = onopen;
	ws_conn.onmessage = onmessage;
	return ws_conn;
}

var file_dlg_result_target = '';
var file_dlg_conn;
var file_dlg_cwd = '';

var file_dlg_headers = {
	'habitat_file_select': "Choose a Habitat Map",
	'habitat_mask_file_select': "Choose a Habitat Mask",
	'short_circuit_file_select': "Choose a Short Circuit Map",
	'focal_nodes_file_select': "Choose a Focal Node Map",
	'incl_excl_file_select': "Choose an Include/Exclude Nodes File",
	'src_strength_file_select': "Choose a file with source strengths",
	'current_sources_file_select': "Choose a file with current sources",
	'ground_points_file_select': "Choose a file with ground points",
};

function file_dlg_list(dir) {
	data = {};
	if(file_dlg_cwd.length > 0) {
		data['cwd'] = file_dlg_cwd;
	}
	if(dir) {
		data['dir'] = dir;
	}
	file_dlg_conn.send(JSON.stringify({
		'msg_type': 1,
		'data': data
	}));				
};

function file_dlg_init(target_id) {
	file_dlg_result_target = target_id.substring(0, target_id.lastIndexOf('_'));
	$('#'+file_dlg_result_target).val('');
	$('#filedlg_div_title').html(file_dlg_headers[target_id]);
	$('#filedlg_div').modal('show');
	$('#filedlg_div').on('hidden.bs.modal', function() {
		if(file_dlg_conn) {
			file_dlg_conn.close();						
		}
	});

	file_dlg_conn = do_ws(file_dlg_list, 
		function(evt) {
			resp = JSON.parse(evt.data);
			if (resp.msg_type == 2) {
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
					sel_file = file_dlg_cwd + "/" + sel_file;
					$('#'+file_dlg_result_target).val(sel_file);
					$('#filedlg_div').modal('hide');
				});
			}
		});
};

function select_input_format(selVal) {
	if(selVal == 'raster') {
		$('.on_raster').show();
		$('.on_network').hide();
	}
	else {
		$('.on_raster').hide();
		$('.on_network').show();
	}
};

function select_modeling_mode(selVal) {
	$('.on_modeling_mode').hide();
	$('.on_modeling_mode').filter($('.on_'+selVal)).show();
};

function logoff() {
	do_ws(function() {
			ws_conn.send(JSON.stringify({
				'msg_type': 3,
				'data': ""
			}));
		},
		function(evt) {
			resp = JSON.parse(evt.data);
			if (resp.msg_type == 4) {
				ws_conn.close();
				$('body').html('<p></p>');
			}
		});
};

function run_verify() {
	do_ws(function() {
			$('#verify_div').modal({ backdrop: 'static', keyboard: false });
			$('#verify_div_msg').val('');
			$('#verify_div').modal('show');
			$('#verify_div_close').attr('disabled', 'disabled');
			ws_conn.send(JSON.stringify({
				'msg_type': 5,
				'data': ""
			}));
		},
		function(evt) {
			resp = JSON.parse(evt.data);
			if (resp.msg_type == 6) {
				alert("complete=" + resp.data.complete);
				alert("success=" + resp.data.success);
				ws_conn.close();
				$('#verify_div_close').removeAttr('disabled');
			}
			else if(resp.msg_type == 0) {
				$('#verify_div_msg').val(resp.data + '\n' + $('#verify_div_msg').val());
			}
		});	
};

function init_circuitscape(ws_url) {
	cs_ws_url = ws_url;
	$('input[id=habitat_file_hidden]').change(function() {
		$('#habitat_file').val($(this).val());
	});
	$('#input_tabs').tab();
	$('#input_tabs a').click(function(e) {
		e.preventDefault();
		$(this).tab('show');
	});
	$('.server_file_dlg').click(function(e){
		file_dlg_init(e.target.id);
	});
	
	$('#num_parallel_procs').spinedit({
		minimum: 1,
		maximum: 10,
		step: 1,
		value: 1,
		numberOfDecimals: 0
	});
	
	select_modeling_mode('pairwise');
	$('#modeling_mode input:radio').change(function() {
		var selVal = $("#modeling_mode input:radio:checked").val();
		select_modeling_mode(selVal);
	});
	
	select_input_format('raster');
	$('#input_format input:radio').change(function() {
		var selVal = $("#input_format input:radio:checked").val();
		select_input_format(selVal);
	});
	
	$('#shutdown').click(function(e){
		$('#logout_div').modal('show');	
	});
	
	$('#menu_verify').click(function(e){
		run_verify();
	});
};
