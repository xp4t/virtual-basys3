# Vivado 2025.1 may expose a newly added cable before its device node exists.
# Reconnect to refresh the client object cache; never declare success on an empty chain.
proc connect_virtual_target {endpoint} {
    set server_url "TCP:localhost:3121"
    if {[info exists ::env(HW_SERVER_URL)]} {
        set server_url $::env(HW_SERVER_URL)
    }
    for {set attempt 1} {$attempt <= 8} {incr attempt} {
        puts "XVC_DISCOVERY: attempt $attempt/8 hw_server=$server_url xvc=$endpoint"
        set connected [catch {
            if {[info exists ::env(HW_SERVER_URL)]} {
                connect_hw_server -url $::env(HW_SERVER_URL)
            } else {
                connect_hw_server
            }
        } reason]
        if {$connected} {
            puts "XVC_DISCOVERY: hw_server connection failed: $reason"
        } elseif {![catch {open_hw_target -xvc_url $endpoint} reason]} {
            set devices [get_hw_devices -quiet]
            if {[llength $devices]} {
                puts "XVC_DISCOVERY: detected [llength $devices] device(s)"
                return $devices
            }
            puts "XVC_DISCOVERY: target opened but returned no devices"
        } else {
            puts "XVC_DISCOVERY: target open failed: $reason"
        }
        # Keep the connection alive while background discovery settles.
        after 3000
        catch {close_hw_target}
        catch {disconnect_hw_server}
    }
    error "XVC discovery failed after eight attempts at $endpoint via $server_url"
}
