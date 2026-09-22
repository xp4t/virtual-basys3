# Run with: vivado -mode batch -source scripts/accept_phase1.tcl
# Environment overrides: XVC_URL (default 127.0.0.1:2542), HW_SERVER_URL.
set endpoint "127.0.0.1:2542"
if {[info exists ::env(XVC_URL)]} { set endpoint $::env(XVC_URL) }
open_hw_manager
source [file join [file dirname [info script]] connect_xvc.tcl]
set devices [connect_virtual_target $endpoint]
if {[llength $devices] != 1} { error "Expected one device, got: $devices" }
set device [lindex $devices 0]
set part [get_property PART $device]
if {$part ne "xc7a35t"} { error "Wrong detected part: $part" }
puts "PHASE1_PASS: Vivado [version -short] detected $device PART=$part via $endpoint"
report_property $device
close_hw_target
disconnect_hw_server
close_hw_manager
exit 0
