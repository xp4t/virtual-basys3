# Vivado 2025.1 may expose a newly added cable before its device node exists.
# Reconnect to refresh the client object cache; never declare success on an empty chain.
proc connect_virtual_target {endpoint} {
    for {set attempt 0} {$attempt < 5} {incr attempt} {
        set connected [catch {
            if {[info exists ::env(HW_SERVER_URL)]} {
                connect_hw_server -url $::env(HW_SERVER_URL)
            } else {
                connect_hw_server
            }
        } reason]
        if {!$connected && ![catch {open_hw_target -xvc_url $endpoint} reason]} {
            set devices [get_hw_devices -quiet]
            if {[llength $devices]} { return $devices }
        }
        # Keep the connection alive while background discovery settles.
        after 3000
        catch {close_hw_target}
        catch {disconnect_hw_server}
    }
    error "XVC discovery failed after five attempts at $endpoint"
}
