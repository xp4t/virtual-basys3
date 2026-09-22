# Optional headless Hardware Manager connection. Ctrl-C stops this process.
set endpoint "127.0.0.1:2542"
if {[info exists ::env(XVC_URL)]} { set endpoint $::env(XVC_URL) }
open_hw_manager
source [file join [file dirname [info script]] connect_xvc.tcl]
set devices [connect_virtual_target $endpoint]
puts "HEADLESS_XVC_READY: $devices on $endpoint; no Vivado GUI"
vwait forever
