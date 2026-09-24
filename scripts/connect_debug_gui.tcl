# Source in a running Vivado GUI. Environment variables select a physical
# cable or a matching XSI-backed virtual target and the design files.
set root [file normalize [file join [file dirname [info script]] ..]]
set design_dir [file join $root build debug_counter]
if {[info exists ::env(DEBUG_DESIGN_DIR)]} {
    set design_dir [file normalize $::env(DEBUG_DESIGN_DIR)]
}
set endpoint "127.0.0.1:2548"
if {[info exists ::env(XVC_URL)]} { set endpoint $::env(XVC_URL) }
set bit_file [file join $design_dir counter.bit]
set ltx_file [file join $design_dir counter.ltx]
if {[info exists ::env(BIT_FILE)]} { set bit_file [file normalize $::env(BIT_FILE)] }
if {[info exists ::env(LTX_FILE)]} { set ltx_file [file normalize $::env(LTX_FILE)] }
foreach path [list $bit_file $ltx_file] {
    if {![file isfile $path]} { error "Missing debug design file: $path" }
}
catch {close_hw_target}
catch {disconnect_hw_server}
open_hw_manager
set target_mode "virtual"
if {[info exists ::env(DEBUG_TARGET)]} { set target_mode $::env(DEBUG_TARGET) }
if {$target_mode eq "physical"} {
    if {![info exists ::env(HW_SERVER_URL)]} {
        set ::env(HW_SERVER_URL) "TCP:127.0.0.1:3121"
    }
    connect_hw_server -url $::env(HW_SERVER_URL)
    set targets {}
    for {set attempt 0} {$attempt < 5} {incr attempt} {
        set targets [get_hw_targets -quiet]
        if {[info exists ::env(HW_TARGET)]} {
            set targets [lsearch -all -inline -glob $targets $::env(HW_TARGET)]
        }
        if {[llength $targets]} { break }
        after 1000
    }
    if {![llength $targets]} {
        error "No physical JTAG target found at $::env(HW_SERVER_URL). Connect and power the Basys3, then reconnect; check HW_TARGET if set."
    }
    if {[llength $targets] != 1} {
        error "Multiple physical hardware targets found: $targets. Set HW_TARGET to its full name or a unique glob pattern."
    }
    open_hw_target [lindex $targets 0]
    set devices [get_hw_devices -quiet]
    set matching_devices {}
    foreach candidate $devices {
        if {[get_property PART $candidate] eq "xc7a35t"} {
            lappend matching_devices $candidate
        }
    }
    set devices $matching_devices
} elseif {$target_mode eq "virtual"} {
    if {![info exists ::env(HW_SERVER_URL)]} {
        set ::env(HW_SERVER_URL) "TCP:127.0.0.1:3127"
    }
    source [file join $root scripts connect_xvc.tcl]
    set devices [connect_virtual_target $endpoint]
} else {
    error "DEBUG_TARGET must be physical or virtual, got $target_mode"
}
if {[llength $devices] != 1} { error "Expected one xc7a35t device: $devices" }
set device [lindex $devices 0]
current_hw_device $device
set_property PROGRAM.FILE $bit_file $device
set_property PROBES.FILE $ltx_file $device
set_property FULL_PROBES.FILE $ltx_file $device
puts "DEBUG_GUI_PROGRAM: BIT=$bit_file LTX=$ltx_file"
program_hw_devices $device
refresh_hw_device $device
set ilas [get_hw_ilas -quiet]
set vios [get_hw_vios -quiet]
set expected_ilas 1
if {[info exists ::env(EXPECTED_ILAS)]} { set expected_ilas $::env(EXPECTED_ILAS) }
set expected_vios 0
if {[info exists ::env(EXPECTED_VIOS)]} { set expected_vios $::env(EXPECTED_VIOS) }
if {[llength $ilas] != $expected_ilas || [llength $vios] != $expected_vios} {
    error "Debug discovery failed: expected $expected_ilas ILA and $expected_vios VIO(s), got [llength $ilas] ILA and [llength $vios] VIO(s)"
}
puts "DEBUG_GUI_READY: $device, [llength $ilas] ILA, [llength $vios] VIO"
