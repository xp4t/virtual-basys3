set root [file normalize [file join [file dirname [info script]] ..]]
set endpoint "127.0.0.1:2542"
if {[info exists ::env(XVC_URL)]} { set endpoint $::env(XVC_URL) }
open_hw_manager
source [file join [file dirname [info script]] connect_xvc.tcl]
set devices [connect_virtual_target $endpoint]
if {[llength $devices] != 1} { error "Expected one device: $devices" }
set device [lindex $devices 0]
current_hw_device $device
set_property PROGRAM.FILE [file join $root build debug_counter counter.bit] $device
set_property PROBES.FILE [file join $root build debug_counter counter.ltx] $device
program_hw_devices $device
refresh_hw_device $device
set ilas [get_hw_ilas -quiet]
set vios [get_hw_vios -quiet]
puts "PHASE5_DISCOVERY: ilas=[llength $ilas] vios=[llength $vios]"
foreach ila $ilas { report_property $ila }
close_hw_target
disconnect_hw_server
close_hw_manager
exit 0
