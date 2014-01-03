// TODO: encapsulate to avoid polluting global namespace

var cs_ws_url = '';
var cs_session = '';

// TODO: generate from server side code
var ws_msg_types = {
	'RSP_ERROR': -1,
    'SHOW_LOG': 0,
    
    'REQ_AUTH': 1000,
    'RSP_AUTH': 1001,
    
    'REQ_FILE_LIST': 101,
    'RSP_FILE_LIST': 102,
    
    'REQ_LOGOUT': 103,
    'RSP_LOGOUT': 104,
    
    'REQ_RUN_VERIFY': 105,
    'RSP_RUN_VERIFY': 106,
    
    'REQ_RUN_JOB': 107,
    'RSP_RUN_JOB': 108,
    
    'REQ_LOAD_CFG': 109,
    'RSP_LOAD_CFG': 110,
    
    'REQ_ABORT_JOB': 111,
    'RSP_ABORT_JOB': 112,
    
    'REQ_RUN_BATCH': 113,
    'RSP_RUN_BATCH': 114,
        
    'REQ_DETACH_TASK': 115,
    'RSP_DETACH_TASK': 116,
    
    'REQ_ATTACH_TASK': 117,
    'RSP_ATTACH_TASK': 118,
    
    'REQ_DETACHED_TASKS': 119,
    'RSP_DETACHED_TASKS': 120,
    
    'REQ_LAST_RUN_LOG': 121,
    'RSP_LAST_RUN_LOG': 122
};

var ws_conn_authenticated = false;
var ws_conn = null;
var ws_conn_onopen = null;
var ws_conn_onmessage = null;
var ws_conn_onclose = null;

function ignore_close_callback() {
	ws_conn_onclose = null;
};

function close_ws(override_callback) {
	if (override_callback) ws_conn_onclose = null;
	ws_conn.close();
};

function send_ws(msg_type, data){
	if(null != ws_conn) {
		ws_conn.send(JSON.stringify({
			'msg_type': msg_type,
			'data': data
		}));		
	}
};

function do_ws(onopen, onmessage, onclose) {
	ws_conn_onopen = onopen;
	ws_conn_onmessage = onmessage;
	ws_conn_onclose = onclose;
	
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
				if(ws_conn_authenticated && (null != ws_conn_onclose)) ws_conn_onclose();
				ws_conn = ws_conn_onopen = ws_conn_onmessage = ws_conn_onclose = null;
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
				'msg_type': ws_msg_types.REQ_LOGOUT,
				'data': {}
			}));
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_LOGOUT) {
				close_ws(true);
				if(!$.cookie("cloudcs_sess")) {
					$('body').html('<p></p>');					
				}
				else {
					$.removeCookie("cloudcs_sess");
					document.location.href = "/";
				}
			}
		}, null);
};

function check_detached_tasks(fn, if_no_tasks) {
	if(cs_session != '') {
		do_ws(function() {
				ws_conn.send(JSON.stringify({
					'msg_type': ws_msg_types.REQ_DETACHED_TASKS,
					'data': {}
				}));
			},
			function(resp) {
				success = false;
				num_tasks = 0;
				if (resp.msg_type == ws_msg_types.RSP_DETACHED_TASKS) {
					success = resp.data.success;
					if(success) num_tasks = resp.data.num_tasks;
				}
				if(!success) {
					alert_in_page('Error determining detached task status.', 'danger');
					close_ws(true);
				}
				else {
					err = if_no_tasks ? (num_tasks > 0) : (num_tasks == 0);
					if(err) {
						msg = if_no_tasks ? 'Your background task is still running. Please wait till it is complete.' : 'You have no running background tasks.';
						alert_in_page(msg, 'warning');
						close_ws(true);
					}
					else {
						fn();
					}
				}
			}, null);
	}
	else {
		fn();
	}
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
				close_ws(true);
			}
		}, null);	
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

function run_job(attach) {
	cfg = {};
	
	if(!attach) {
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
	}
	
	do_ws(function() {
			$('#results_div').modal({ backdrop: 'static', keyboard: false });
			$('#results_div_title').html('Running...');
			$('#results_div_msg').val('');
			$('#results_div').modal('show');
			$('#results_div_close').attr('disabled', 'disabled');
			$('#btn_abort_run').removeAttr('disabled');
			$('#btn_detach_run').removeAttr('disabled');
			if(!attach) {
				ws_conn.send(JSON.stringify({
					'msg_type': ws_msg_types.REQ_RUN_JOB,
					'data': {
						'run_data': cfg,
						'client_ctx': 'job'
					}
				}));				
			}
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_RUN_JOB) {
				$('#results_div_msg').val((resp.data.success ? 'Success' : 'Failed') + '.\n' + $('#results_div_msg').val());
				close_ws(true);
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
				$('#btn_detach_run').attr('disabled', 'disabled');
			}
			else if(resp.msg_type == ws_msg_types.RSP_DETACH_TASK) {
				close_ws(true);
			}
			else if(resp.msg_type == ws_msg_types.SHOW_LOG) {
				$('#results_div_msg').val(resp.data + '\n' + $('#results_div_msg').val());
			}
			else if(resp.msg_type == ws_msg_types.RSP_ERROR) {
				$('#results_div_msg').val('Error: ' + resp.data + '\n' + $('#results_div_msg').val());
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
				$('#btn_detach_run').attr('disabled', 'disabled');
				ignore_close_callback();
			}
		},
		function() {
			alert_in_page("Disconnected from server. To see results use the 'Monitor Background Task' or 'Show Previous Task Logs' menu options.", "warning");
			$('#results_div').modal('hide');
		});	
};

function run_batch(foldername, attach) {
	do_ws(function() {
			$('#results_div').modal({ backdrop: 'static', keyboard: false });
			$('#results_div_title').html('Running Batch...');
			$('#results_div_msg').val('');
			$('#results_div').modal('show');
			$('#results_div_close').attr('disabled', 'disabled');
			$('#btn_abort_run').removeAttr('disabled');
			$('#btn_detach_run').removeAttr('disabled');
			if(!attach) {
				ws_conn.send(JSON.stringify({
					'msg_type': ws_msg_types.REQ_RUN_BATCH,
					'data': {
						'run_data': foldername,
						'client_ctx': 'batch'
					}
				}));				
			}
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_RUN_BATCH) {
				$('#results_div_msg').val((resp.data.success ? 'Success' : 'Failed') + '.\n' + $('#results_div_msg').val());
				close_ws(true);
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
				$('#btn_detach_run').attr('disabled', 'disabled');
			}
			else if(resp.msg_type == ws_msg_types.RSP_DETACH_TASK) {
				close_ws(true);
			}
			else if(resp.msg_type == ws_msg_types.SHOW_LOG) {
				$('#results_div_msg').val(resp.data + '\n' + $('#results_div_msg').val());
			}
			else if(resp.msg_type == ws_msg_types.RSP_ERROR) {
				$('#results_div_msg').val('Error: ' + resp.data + '\n' + $('#results_div_msg').val());
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
				$('#btn_detach_run').attr('disabled', 'disabled');
				ignore_close_callback();
			}
		},
		function() {
			alert_in_page("Disconnected from server. Use 'Monitor Background Task' or 'Show Previous Task Logs' menu options to examine logs.", "warning");
			$('#results_div').modal('hide');
		});		
};

function run_verify(attach) {
	do_ws(function() {
			$('#results_div').modal({ backdrop: 'static', keyboard: false });
			$('#results_div_title').html('Running Verifications...');
			$('#results_div_msg').val('');
			$('#results_div').modal('show');
			$('#results_div_close').attr('disabled', 'disabled');
			$('#btn_abort_run').removeAttr('disabled');
			$('#btn_detach_run').removeAttr('disabled');
			if(!attach) {
				ws_conn.send(JSON.stringify({
					'msg_type': ws_msg_types.REQ_RUN_VERIFY,
					'data': {
						'run_data': "",
						'client_ctx': 'verify'
					}
				}));				
			}
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_RUN_VERIFY) {
				if(resp.data.success) {
					$('#results_div_msg').val('All tests passed.\n' + $('#results_div_msg').val());
				}
				else {
					$('#results_div_msg').val('Tests failed.\n' + $('#results_div_msg').val());
				}
				close_ws(true);
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
				$('#btn_detach_run').attr('disabled', 'disabled');
			}
			else if(resp.msg_type == ws_msg_types.RSP_DETACH_TASK) {
				close_ws(true);
			}
			else if(resp.msg_type == ws_msg_types.SHOW_LOG) {
				$('#results_div_msg').val(resp.data + '\n' + $('#results_div_msg').val());
			}
			else if(resp.msg_type == ws_msg_types.RSP_ERROR) {
				$('#results_div_msg').val('Error: ' + resp.data + '\n' + $('#results_div_msg').val());
				$('#results_div_close').removeAttr('disabled');
				$('#btn_abort_run').attr('disabled', 'disabled');
				$('#btn_detach_run').attr('disabled', 'disabled');
				ignore_close_callback();
			}
		},
		function() {
			alert_in_page("Disconnected from server. Use 'Monitor Background Task' or 'Show Previous Task Logs' menu options to examine logs.", "warning");
			$('#results_div').modal('hide');
		});	
};

function show_last_run_log() {
	do_ws(function() {
			$('#results_div').modal({ backdrop: 'static', keyboard: false });
			$('#results_div_title').html('Logs from your last run');
			$('#results_div_msg').val('');
			$('#results_div').modal('show');
			$('#results_div_close').attr('disabled', 'disabled');
			$('#btn_abort_run').attr('disabled', 'disabled');
			$('#btn_detach_run').attr('disabled', 'disabled');
			ws_conn.send(JSON.stringify({
				'msg_type': ws_msg_types.REQ_LAST_RUN_LOG,
				'data': {}
			}));				
		},
		function(resp) {
			if (resp.msg_type == ws_msg_types.RSP_LAST_RUN_LOG) {
				if(!resp.data.success) {
					$('#results_div_msg').val(resp.data.msg + '\n' + $('#results_div_msg').val());
				}
				ws_conn.close();
				$('#results_div_close').removeAttr('disabled');
			}
			else if(resp.msg_type == ws_msg_types.SHOW_LOG) {
				$('#results_div_msg').val(resp.data + '\n' + $('#results_div_msg').val());
			}
			else if(resp.msg_type == ws_msg_types.RSP_ERROR) {
				$('#results_div_msg').val('Error: ' + resp.data + '\n' + $('#results_div_msg').val());
				$('#results_div_close').removeAttr('disabled');
			}
		},
		null);	
};
function abort_run() {
	if(cs_session != '') $('#btn_detach_run').attr('disabled', 'disabled');
	send_ws(ws_msg_types.REQ_ABORT_JOB, "");
};

function detach_run() {
	if(cs_session != '') $('#btn_abort_run').attr('disabled', 'disabled');
	send_ws(ws_msg_types.REQ_DETACH_TASK, "");
};

function attach_run() {
	do_ws(function() {
		ws_conn.send(JSON.stringify({
			'msg_type': ws_msg_types.REQ_ATTACH_TASK,
			'data': {}
		}));
	},
	function(resp) {
		if(resp.msg_type == ws_msg_types.RSP_ATTACH_TASK) {
			if(resp.data.success) {
				client_ctx = resp.data.client_ctx;
				if(client_ctx == 'verify') {
					run_verify(true);
				}
				else if(client_ctx == 'batch') {
					run_batch('', true);
				}
				else if(client_ctx == 'job') {
					run_job(true);
				}
			}
			else {
				alert_in_page("Error attaching to background task.", "danger");
			}
		}
	},
	null);
};

function alert_in_page(msg, level) {
	$('#in_page_alert_msg').html(msg);
	$('#in_page_alert').removeClass("alert-success alert-info alert-warning alert-danger");
	$('#in_page_alert').addClass("alert-"+level);
	$('#in_page_alert').show();
};

var TOOLTIPS = {
	'btn_run' : 'Run with the chosen configuration.',
	//'input_format_raster': 'Raster map of resistances',
	//'input_format_network': 'Network of nodes connected by links',
	'input_format': ['Choose an input format,<br/> raster map of resistances or <br/>network of connected nodes', 'right'],
	'preemptive_memory_release_div': 'Intermittently pause to release unused memory.',
	'low_memory_mode_div': 'Recompute memory intensive data whenever possible instead of caching in memory.',
	'log_level': ['Verbosity of messages during execution.', 'top'],
	'print_rusages_div': 'Log machine resources consumed at critical steps. Helps in debugging/fine tuning.',
	'print_timings_div': 'Log time taken at critical steps. Helps in debugging/fine tuning.',
	'use_max_parallel_div': 'Use all available processors on the machine'
};

function create_tooltips() {		
	for(elem_id in TOOLTIPS) {
		options = {
			'trigger': 'hover',
			'delay': 100,
		};
		
		settings = TOOLTIPS[elem_id];
		if($.isArray(settings)) {
			options['title'] = settings[0];
			options['placement'] = settings[1];
		}
		else {
			options['title'] = settings;
		}
		if ((options['title']).indexOf('<') != -1) options['html'] = true;
		
		
		$('#'+elem_id).tooltip(options);	
	}
};

function init_circuitscape(ws_url, sess_id) {
	cs_ws_url = ws_url;
	cs_session = sess_id;
	$('#in_page_alert').hide();
	$('#menu_load_file').change(function(){
		load_cfg($('#menu_load_file').val());
	});
	$('#menu_batch_folder').change(function(){
		$('#in_page_alert').hide();
		batch_file_name = $('#menu_batch_folder').val();
		check_detached_tasks(function() {
			run_batch(batch_file_name, false);			
		}, true);
	});
	$('#menu_reattach').click(function() {
		$('#in_page_alert').hide();
		check_detached_tasks(function() {
			attach_run();			
		}, false);
	});
	$('#menu_show_last_logs').click(function() {
		$('#in_page_alert').hide();
		check_detached_tasks(function() {
			show_last_run_log();			
		}, true);
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
		$('#in_page_alert').hide();
		check_detached_tasks(function(){
			run_verify(false);
		}, true);
	});
	
	$('#btn_run').click(function(e){
		$('#in_page_alert').hide();
		check_detached_tasks(function(){
			run_job(false);
		}, true);
	});
	
	$('#btn_abort_run').click(function(e){
		abort_run();
	});
	
	$('#btn_detach_run').click(function(e){
		detach_run();
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
	
	create_tooltips();
};
