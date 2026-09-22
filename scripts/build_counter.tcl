set root [file normalize [file join [file dirname [info script]] ..]]
set output [file join $root build counter]
set include_ila [expr {[info exists ::env(INCLUDE_ILA)] && $::env(INCLUDE_ILA) eq "1"}]
if {$include_ila} { set output [file join $root build debug_counter] }
# Debug-core out-of-context synthesis is memory hungry on small hosts.
if {$include_ila} { set_param general.maxThreads 2 }
file mkdir $output
create_project -in_memory -part xc7a35tcpg236-1
read_verilog [file join $root examples counter counter.v]
# Set port constraints after synthesis in the non-project flow.
synth_design -top counter -part xc7a35tcpg236-1
set f [open [file join $root references Basys-3-Master.xdc] r]
foreach line [split [read $f] "\n"] {
    if {[regexp {^#(set_property -dict .*\[get_ports (clk|btnC|\{sw\[[0-9]+\]\}|\{led\[[0-9]+\]\})\])} $line -> command]} {
        eval $command
    }
}
close $f
create_clock -period 10.000 [get_ports clk]
if {$include_ila} {
    create_debug_core ila0 ila
    set_property C_DATA_DEPTH 1024 [get_debug_cores ila0]
    set_property C_TRIGIN_EN false [get_debug_cores ila0]
    set_property C_TRIGOUT_EN false [get_debug_cores ila0]
    set_property port_width 8 [get_debug_ports ila0/probe0]
    # Synthesis can rename count[] to the LED output-buffer nets. Probe the
    # register Q pins instead of relying on the RTL net aliases surviving.
    set counter_registers [lsort -dictionary [get_cells -hier -filter {REF_NAME == FDRE && NAME =~ *count_reg*}]]
    set counter_nets {}
    foreach cell $counter_registers {
        lappend counter_nets [get_nets -of_objects [get_pins -of_objects $cell -filter {REF_PIN_NAME == Q}]]
    }
    if {[llength $counter_nets] != 8} { error "Expected eight counter probe nets: $counter_nets" }
    connect_debug_port ila0/probe0 $counter_nets
    connect_debug_port ila0/clk [get_nets clk_IBUF_BUFG]
    set_property C_CLK_INPUT_FREQ_HZ 100000000 [get_debug_cores dbg_hub]
    set_property C_USER_SCAN_CHAIN 1 [get_debug_cores dbg_hub]
    connect_debug_port dbg_hub/clk [get_nets clk_IBUF_BUFG]
}
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property BITSTREAM.STARTUP.STARTUPCLK JtagClk [current_design]
set_property BITSTREAM.GENERAL.COMPRESS FALSE [current_design]
opt_design
place_design
route_design
write_checkpoint -force [file join $output counter.dcp]
write_bitstream -force [file join $output counter.bit]
if {$include_ila} { write_debug_probes -force [file join $output counter.ltx] }
report_timing_summary -file [file join $output timing.rpt]
puts "COUNTER_BUILD_PASS: [file join $output counter.bit]"
exit 0
