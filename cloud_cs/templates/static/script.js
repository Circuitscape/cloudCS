// TODO: encapsulate to avoid polluting global namespace

var cs_ws_url = '';
var cs_session = '';

// TODO: generate from server side code
var ws_msg_types = {
	'RSP_ERROR': -1,
    'SHOW_LOG': 0,
    
    'REQ_AUTH': 1000,
    'RSP_AUTH': 1001,
    
    'REQ_FILE_LIST': 1,
    'RSP_FILE_LIST': 2,
    
    'REQ_LOGOUT': 3,
    'RSP_LOGOUT': 4,
    
    'REQ_RUN_VERIFY': 5,
    'RSP_RUN_VERIFY': 6,
    
    'REQ_RUN_JOB': 7,
    'RSP_RUN_JOB': 8,
    
    'REQ_LOAD_CFG': 9,
    'RSP_LOAD_CFG': 10,
    
    'REQ_ABORT_JOB': 11,
    'RSP_ABORT_JOB': 12
};

var ws_conn_authenticated = false;
var ws_conn = null;
var ws_conn_onopen = null;
var ws_conn_onmessage = null;

function send_ws(msg_type, data){
	if(null != ws_conn) {
		ws_conn.send(JSON.stringify({
			'msg_type': msg_type,
			'data': data
		}));		
	}
}

function do_ws(onopen, onmessage) {
	ws_conn_onopen = onopen;
	ws_conn_onmessage = onmessage;
	
	if(cs_session != '') {
		if(null == ws_conn) {
			var ws_conn_authenticated = false;
			ws_conn = new WebSocket(cs_ws_url);
			ws_conn.onopen = function(evt) {
				ws_conn.send(JSON.stringify({
					'msg_type': ws_msg_types.REQ_AUTH,
					'data': {'sess_id': cs_session}
				}));
			};
			
			ws_conn.onclose = function(evt) {
				ws_conn = ws_conn_onopen = ws_conn_onmessage = null;
				ws_conn_authenticated = false;
			};
			
			ws_conn.onmessage = function(evt) {
				resp = JSON.parse(evt.data);
				if(ws_conn_authenticated) {
					if(null != ws_conn_onmessage) ws_conn_onmessage(resp);
				}
				else {
					if (resp.msg_type == ws_msg_types.RSP_AUTH) {
						ws_conn_authenticated = resp.data.success;
						if(ws_conn_authenticated && (null != ws_conn_onopen)) ws_conn_onopen();
					}
				}
			};
		}
		else {
			ws_conn_onopen();
		}
	}
	else {
		ws_conn = new WebSocket(cs_ws_url);
		ws_conn.onopen = function(evt) {
			ws_conn_onopen();
		};
		ws_conn.onmessage = function(evt) {
			resp = JSON.parse(evt.data);
			ws_conn_onmessage(resp);
		};
	}
}

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
				'msg_type': ws_msg_types.REQ_LOGOUT,
				'data': {}
			}));
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_LOGOUT) {
				ws_conn.close();
				if(!$.cookie("cloudcs_sess")) {
					$('body').html('<p></p>');					
				}
				else {
					$.removeCookie("cloudcs_sess");
					document.location.href = "/";
				}
			}
		});
};

function get_form_field(fld_name, fld_type) {
	selector = '#' + fld_name;
	if(fld_type=='radio') {
		selector = 'input[name=' + fld_name + ']:radio:checked';			
	}
	return (fld_type == 'checkbox') ? $(selector).is(':checked') : $.trim($(selector).val());		
};

function set_form_field(fld_name, fld_val, fld_type) {
	if(get_form_field(fld_name, fld_type) == fld_val) {
		return;
	}
	selector = '#' + fld_name;
	if(fld_type=='radio') {
		selector = "input[name=" + fld_name + "]";
		$(selector).filter("[value='"+fld_val+"']").click();
		//$(selector).filter("[value='"+fld_val+"']").attr("checked","checked");
	}
	else if(fld_type == 'checkbox') {
		if(fld_val) {
			$(selector).attr('checked', 'checked');			
		}
		else {
			$(selector).removeAttr('checked');
		}
		//$(selector).click();
	}
	else {
		$(selector).val(fld_val);
		$(selector).change();			
	}
};

function load_cfg(filename) {
	alert_in_page('Loading configuration from ' + filename + '...', 'info');
	$('#btn_run').attr('disabled', 'disabled');
	do_ws(function() {
			ws_conn.send(JSON.stringify({
				'msg_type': ws_msg_types.REQ_LOAD_CFG,
				'data': {'filename': filename}
			}));
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_LOAD_CFG) {
				$('#btn_run').removeAttr('disabled');
				if(resp.data.success) {
					alert_in_page('Loaded configuration from ' + filename, 'success');
					populate_config(resp.data.cfg);
				}
				else {
					alert_in_page('Error loading configuration. ' + resp.data.cfg, 'danger');
				}
				ws_conn.close();
			}
		});	
};

function populate_config(cfg) {
	set_form_field('input_type', cfg.data_type, 'radio');
	select_input_format(cfg.data_type);		

	set_form_field('radio_modeling_mode', cfg.scenario, 'radio');
	select_modeling_mode(cfg.scenario);
	
	if(cfg.data_type == 'raster') {
		set_form_field('cell_conn_type', cfg.connect_four_neighbors_only ? 4 : 8);
		set_form_field('cell_calc_type', cfg.connect_using_avg_resistances ? 'R' : 'C');
		set_form_field('short_circuit_file', cfg.use_polygons ? cfg.polygon_file : ''); 
		set_form_field('habitat_mask_file', cfg.use_mask ? cfg.mask_file : '');
	}
	set_form_field('habitat_file', cfg.habitat_file);
	set_form_field('habitat_data_type', cfg.habitat_map_is_resistances ? 'R' : 'C');

	if(cfg.scenario == 'advanced') {
		set_form_field('current_sources_file', cfg.source_file);
		set_form_field('ground_points_file', cfg.ground_file);
		set_form_field('ground_value_type', cfg.ground_file_is_resistances ? 'R':'C');
		set_form_field('use_unit_currents', cfg.use_unit_currents, 'checkbox');
		set_form_field('chk_use_direct_grounds', cfg.use_direct_grounds, 'checkbox');
		set_form_field('rmv_on_conflict', cfg.remove_src_or_gnd);
	}
	
	if((cfg.scenario == 'one-to-all') || (cfg.scenario == 'all-to-one')) {
		set_form_field('src_strength_file', cfg.use_variable_source_strengths ? cfg.variable_source_file : '');
	}

	if((cfg.scenario != 'advanced')) {
		set_form_field('focal_nodes_file', cfg.point_file);
		
		set_form_field('incl_excl_file', cfg.use_included_pairs ? cfg.included_pairs_file : '');
		set_form_field('write_cum_cur_map_only', cfg.write_cum_cur_map_only, 'checkbox');
		set_form_field('write_max_cur_maps', cfg.write_max_cur_maps, 'checkbox');
	}
	
	if(cfg.scenario == 'pairwise') {
		num_parallel_procs = set_form_field('num_parallel_procs', cfg.parallelize ? cfg.max_parallel : '1');

		if(cfg.parallelize && (cfg.max_parallel == 0)) {
			set_form_field('use_max_parallel', true, 'checkbox');
			$('#num_parallel_procs').spinedit('setMinimum', 0);
			$('#num_parallel_procs').spinedit('setMaximum', 0);
			$('#num_parallel_procs').spinedit('setStep', 0);
			$('#num_parallel_procs').spinedit('setValue', 0);
		}
		else {
			set_form_field('use_max_parallel', false, 'checkbox');
			$('#num_parallel_procs').spinedit('setMinimum', 1);
			$('#num_parallel_procs').spinedit('setMaximum', 10);
			$('#num_parallel_procs').spinedit('setStep', 1);
			$('#num_parallel_procs').spinedit('setValue', num_parallel_procs);
		}
		set_form_field('low_memory_mode', cfg.low_memory_mode, 'checkbox');
	}
	set_form_field('preemptive_memory_release', cfg.preemptive_memory_release, 'checkbox');
	set_form_field('print_timings', cfg.print_timings, 'checkbox');
	set_form_field('print_rusages', cfg.print_rusages, 'checkbox');
	set_form_field('log_level', cfg.log_level);
	set_form_field('log_transform_maps', cfg.log_transform_maps, 'checkbox');
	set_form_field('compress_grids', cfg.compress_grids, 'checkbox');
	set_form_field('write_volt_maps', cfg.write_volt_maps, 'checkbox');
	set_form_field('write_cur_maps', cfg.write_cur_maps, 'checkbox');
	set_form_field('output_file', cfg.output_file);
}

function run_job() {
	cfg = {};
	cfg.data_type = get_form_field('input_type', 'radio');
	cfg.scenario = get_form_field('radio_modeling_mode', 'radio');
	
	if(cfg.data_type == 'raster') {
		cfg.connect_four_neighbors_only = (get_form_field('cell_conn_type') == 4);
		cfg.connect_using_avg_resistances = (get_form_field('cell_calc_type') == 'R');
		
		filename = get_form_field('short_circuit_file');
		if(filename.length > 0) {
			cfg.use_polygons = true;
			cfg.polygon_file = filename;
		}

		filename = 	get_form_field('habitat_mask_file');
		if(filename.length > 0) {
			cfg.mask_file = filename; 
			cfg.use_mask = true;
		}
	}

	filename = 	get_form_field('habitat_file');
    if(filename.length > 0) {
    	cfg.habitat_file = filename;
    	cfg.habitat_map_is_resistances = (get_form_field('habitat_data_type') == 'R');
    }
	
	if(cfg.scenario == 'advanced') {
		filename = 	get_form_field('current_sources_file');
		if(filename.length > 0) cfg.source_file = filename;

		filename = 	get_form_field('ground_points_file');
		if(filename.length > 0) cfg.ground_file = filename;
		
		cfg.ground_file_is_resistances = (get_form_field('ground_value_type') == 'R');
		cfg.use_unit_currents = get_form_field('use_unit_currents', 'checkbox');
		cfg.use_direct_grounds = get_form_field('chk_use_direct_grounds', 'checkbox');
		cfg.remove_src_or_gnd = get_form_field('rmv_on_conflict');
	}
	
	if((cfg.scenario == 'one-to-all') || (cfg.scenario == 'all-to-one')) {
		filename = 	get_form_field('src_strength_file');
		if(filename.length > 0) {
        	cfg.use_variable_source_strengths = true; 
            cfg.variable_source_file = filename;
		}
	}

	if((cfg.scenario != 'advanced')) {
		filename = 	get_form_field('focal_nodes_file');
		if(filename.length > 0) {
			cfg.point_file = filename;
		}
		
		filename = get_form_field('incl_excl_file');
		if(filename.length > 0) {
			cfg.use_included_pairs = true;
			cfg.included_pairs_file = filename;
		}
		cfg.write_cum_cur_map_only = get_form_field('write_cum_cur_map_only', 'checkbox');
		cfg.write_max_cur_maps = get_form_field('write_max_cur_maps', 'checkbox');
	}
	
	if(cfg.scenario == 'pairwise') {
		num_parallel_procs = get_form_field('num_parallel_procs');
		if(num_parallel_procs != 1) {
			cfg.parallelize = true;
			cfg.max_parallel = parseInt(num_parallel_procs);
		}
		cfg.low_memory_mode = get_form_field('low_memory_mode', 'checkbox');
	}
	cfg.preemptive_memory_release = get_form_field('preemptive_memory_release', 'checkbox');
	cfg.print_timings = get_form_field('print_timings', 'checkbox');
	cfg.print_rusages = get_form_field('print_rusages', 'checkbox');
	cfg.log_level = get_form_field('log_level');
	cfg.log_transform_maps = get_form_field('log_transform_maps', 'checkbox');
	cfg.compress_grids = get_form_field('compress_grids', 'checkbox');
	cfg.write_volt_maps = get_form_field('write_volt_maps', 'checkbox');
	cfg.write_cur_maps = get_form_field('write_cur_maps', 'checkbox');
	cfg.output_file = get_form_field('output_file');
	
	do_ws(function() {
			$('#results_div').modal({ backdrop: 'static', keyboard: false });
			$('#results_div_title').html('Running...');
			$('#results_div_msg').val('');
			$('#results_div').modal('show');
			$('#results_div_close').attr('disabled', 'disabled');
			$('#btn_abort_run').removeAttr('disabled');
			ws_conn.send(JSON.stringify({
				'msg_type': ws_msg_types.REQ_RUN_JOB,
				'data': cfg
			}));
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_RUN_JOB) {
				$('#results_div_msg').val((resp.data.success ? 'Success' : 'Failed') + '.\n' + $('#results_div_msg').val());
				ws_conn.close();
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
			}
			else if(resp.msg_type == ws_msg_types.SHOW_LOG) {
				$('#results_div_msg').val(resp.data + '\n' + $('#results_div_msg').val());
			}
			else if(resp.msg_type == ws_msg_types.RSP_ERROR) {
				$('#results_div_msg').val('Error: ' + resp.data + '\n' + $('#results_div_msg').val());
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
			}
		});	
};

function run_verify() {
	do_ws(function() {
			$('#results_div').modal({ backdrop: 'static', keyboard: false });
			$('#results_div_title').html('Running Verifications...');
			$('#results_div_msg').val('');
			$('#results_div').modal('show');
			$('#results_div_close').attr('disabled', 'disabled');
			$('#btn_abort_run').removeAttr('disabled');
			ws_conn.send(JSON.stringify({
				'msg_type': ws_msg_types.REQ_RUN_VERIFY,
				'data': ""
			}));
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_RUN_VERIFY) {
				if(resp.data.success) {
					$('#results_div_msg').val('All tests passed.\n' + $('#results_div_msg').val());
				}
				else {
					$('#results_div_msg').val('Tests failed.\n' + $('#results_div_msg').val());
				}
				ws_conn.close();
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
			}
			else if(resp.msg_type == ws_msg_types.SHOW_LOG) {
				$('#results_div_msg').val(resp.data + '\n' + $('#results_div_msg').val());
			}
			else if(resp.msg_type == ws_msg_types.RSP_ERROR) {
				$('#results_div_msg').val('Error: ' + resp.data + '\n' + $('#results_div_msg').val());
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
			}
		});	
};

function abort_run() {
	send_ws(ws_msg_types.REQ_ABORT_JOB, "");
};

function alert_in_page(msg, level) {
	$('#in_page_alert_msg').html(msg);
	$('#in_page_alert').removeClass("alert-success alert-info alert-warning alert-danger");
	$('#in_page_alert').addClass("alert-"+level);
	$('#in_page_alert').show();
};

function init_circuitscape(ws_url, sess_id) {
	cs_ws_url = ws_url;
	cs_session = sess_id;
	$('#in_page_alert').hide();
	$('#menu_load_file').hide();
	$('#menu_load_file').change(function(){
		load_cfg($('#menu_load_file').val());
	});
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
	$('#btn_filedlg_div_sel').click(function(e){
		sel_file = file_dlg_cwd + "/" + $('#filedlg_filename').val();
		$('#'+file_dlg_result_target).val(sel_file);
		$('#'+file_dlg_result_target).change();
		$('#filedlg_div').modal('hide');		
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
	
	$('#btn_run').click(function(e){
		$('#in_page_alert').hide();
		run_job();
	});
	
	$('#btn_abort_run').click(function(e){
		abort_run();
	});
	
	$('#use_max_parallel').click(function(e){
		max_parallel = get_form_field('use_max_parallel', 'checkbox');
		if(max_parallel) {
			set_form_field('num_parallel_procs', '0');
			$('#num_parallel_procs').spinedit('setMinimum', 0);
			$('#num_parallel_procs').spinedit('setMaximum', 0);
			$('#num_parallel_procs').spinedit('setStep', 0);
			$('#num_parallel_procs').spinedit('setValue', 0);
		}
		else {
			set_form_field('num_parallel_procs', '1');
			$('#num_parallel_procs').spinedit('setMinimum', 1);
			$('#num_parallel_procs').spinedit('setMaximum', 10);
			$('#num_parallel_procs').spinedit('setStep', 1);
			$('#num_parallel_procs').spinedit('setValue', 1);
		}
	});
};
