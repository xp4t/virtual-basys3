# Counter fixture acceptance, invoked by probe_phase5.tcl with DEBUG_ACCEPT=1.
if {[llength $ilas] != 1} { error "Counter acceptance requires exactly one ILA" }
set ila [lindex $ilas 0]
foreach {property expected} {
    STATIC.MAX_DATA_DEPTH 1024
    STATIC.PORTS.COUNT 1
    STATIC.PORTS.PORT_0.WIDTH 8
} {
    set actual [get_property $property $ila]
    if {$actual != $expected} { error "$ila $property: expected $expected, got $actual" }
}

proc capture_counter {ila path} {
    set_property CONTROL.DATA_DEPTH 1024 $ila
    set_property CONTROL.TRIGGER_POSITION 0 $ila
    run_hw_ila -trigger_now $ila
    wait_on_hw_ila -timeout 600 $ila
    set data [upload_hw_ila_data $ila]
    write_hw_ila_data -force -csv_file $path $data
}

if {[llength $vios]} {
    set vio [lindex $vios 0]
    set control [get_hw_probes -quiet *debug_control* -of_objects $vio]
    set input [get_hw_probes -quiet *count* -of_objects $vio]
    if {[llength $control] != 1 || [llength $input] != 1} {
        error "Expected counter input and debug_control output in VIO LTX probes"
    }
    set_property OUTPUT_VALUE 2 $control
    commit_hw_vio $vio
    refresh_hw_vio $vio
    if {[get_property INPUT_VALUE $input] != 0} { error "VIO reset did not clear the counter" }
    set_property OUTPUT_VALUE 0 $control
    commit_hw_vio $vio
    set stopped_csv [file join $design_dir stopped.csv]
    capture_counter $ila $stopped_csv
    puts [exec python3 [file join $root scripts check_ila_csv.py] $stopped_csv --mode stopped]
    set_property OUTPUT_VALUE 1 $control
    commit_hw_vio $vio
    puts "PHASE5_VIO_PASS: reset, input readback, hold, and enable"
}
set capture_csv [file join $design_dir capture.csv]
capture_counter $ila $capture_csv
puts [exec python3 [file join $root scripts check_ila_csv.py] $capture_csv --mode counting]
puts "PHASE5_ACCEPT_PASS: $ltx_file"
