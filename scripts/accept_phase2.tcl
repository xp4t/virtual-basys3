set root [file normalize [file join [file dirname [info script]] ..]]
set endpoint "127.0.0.1:2542"
if {[info exists ::env(XVC_URL)]} { set endpoint $::env(XVC_URL) }
set bitstream [file join $root build counter counter.bit]
if {[llength $argv]} { set bitstream [file normalize [lindex $argv 0]] }
if {![file exists $bitstream]} { error "Missing bitstream: $bitstream" }
open_hw_manager
source [file join [file dirname [info script]] connect_xvc.tcl]
set devices [connect_virtual_target $endpoint]
if {[llength $devices] != 1} { error "Expected one device: $devices" }
set device [lindex $devices 0]
if {[get_property PART $device] ne "xc7a35t"} { error "Wrong target part" }
current_hw_device $device
set_property PROGRAM.FILE $bitstream $device
set_property PROBES.FILE {} $device
program_hw_devices $device
refresh_hw_device -update_hw_probes false $device
foreach property {
    REGISTER.IR.BIT5_DONE
    REGISTER.CONFIG_STATUS.BIT12_INIT_B_PIN
    REGISTER.CONFIG_STATUS.BIT14_DONE_PIN
    REGISTER.CONFIG_STATUS.BIT04_END_OF_STARTUP_(EOS)_STATUS
} {
    if {[get_property $property $device] ne "1"} { error "$property is not 1" }
}
foreach property {
    REGISTER.CONFIG_STATUS.BIT00_CRC_ERROR
    REGISTER.CONFIG_STATUS.BIT15_IDCODE_ERROR
    REGISTER.CONFIG_STATUS.BIT16_SECURITY_ERROR
} {
    if {[get_property $property $device] ne "0"} { error "$property is not 0" }
}
puts "PHASE2_PASS: Vivado [version -short] programmed $bitstream; DONE/INIT_B/EOS=1"
report_property $device
close_hw_target
disconnect_hw_server
close_hw_manager
exit 0
