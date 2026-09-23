set root [file normalize [file join [file dirname [info script]] ..]]
set endpoint "127.0.0.1:2542"
if {[info exists ::env(XVC_URL)]} { set endpoint $::env(XVC_URL) }
set design_dir [file join $root build debug_counter]
if {[info exists ::env(DEBUG_DESIGN_DIR)]} { set design_dir [file normalize $::env(DEBUG_DESIGN_DIR)] }
set bit_file [file join $design_dir counter.bit]
set ltx_file [file join $design_dir counter.ltx]
if {[info exists ::env(BIT_FILE)]} { set bit_file [file normalize $::env(BIT_FILE)] }
if {[info exists ::env(LTX_FILE)]} { set ltx_file [file normalize $::env(LTX_FILE)] }
foreach path [list $bit_file $ltx_file] {
    if {![file isfile $path]} { error "Missing debug design file: $path" }
}
open_hw_manager
source [file join [file dirname [info script]] connect_xvc.tcl]
set devices [connect_virtual_target $endpoint]
if {[llength $devices] != 1} { error "Expected one device: $devices" }
set device [lindex $devices 0]
current_hw_device $device
set_property PROGRAM.FILE $bit_file $device
set_property PROBES.FILE $ltx_file $device
set_property FULL_PROBES.FILE $ltx_file $device
if {![info exists ::env(SKIP_PROGRAM)] || $::env(SKIP_PROGRAM) ne "1"} {
    program_hw_devices $device
}
refresh_hw_device $device
set ilas [get_hw_ilas -quiet]
set vios [get_hw_vios -quiet]
puts "PHASE5_DISCOVERY: ilas=[llength $ilas] vios=[llength $vios]"
set expected_ilas 1
set expected_vios 0
if {[info exists ::env(EXPECTED_ILAS)]} { set expected_ilas $::env(EXPECTED_ILAS) }
if {[info exists ::env(EXPECTED_VIOS)]} { set expected_vios $::env(EXPECTED_VIOS) }
if {[llength $ilas] != $expected_ilas || [llength $vios] != $expected_vios} {
    error "Debug discovery failed: expected $expected_ilas ILA(s) and $expected_vios VIO(s)"
}
foreach core [concat $ilas $vios] {
    if {[get_property CELL_NAME $core] eq "" ||
        ![llength [get_hw_probes -quiet -of_objects $core]]} {
        error "No LTX probes matched debug core $core in $ltx_file"
    }
}
foreach ila $ilas { report_property $ila }
foreach vio $vios { report_property $vio }
puts "PHASE5_PROBES_PASS: $ltx_file"
if {[info exists ::env(DEBUG_ACCEPT)] && $::env(DEBUG_ACCEPT) eq "1"} {
    source [file join $root scripts check_debug_counter.tcl]
}
close_hw_target
disconnect_hw_server
close_hw_manager
exit 0
