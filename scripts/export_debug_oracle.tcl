set root [file normalize [file join [file dirname [info script]] ..]]
set output [file join $root build debug_counter]
open_checkpoint [file join $output counter.dcp]
set bscan [get_cells -hier -filter {REF_NAME == BSCANE2}]
if {[llength $bscan] != 1} { error "Expected one BSCANE2: $bscan" }
puts "DEBUG_ORACLE_BSCAN: $bscan loc=[get_property LOC $bscan] bel=[get_property BEL $bscan]"
write_verilog -force -mode funcsim [file join $output funcsim.v]
exit 0
