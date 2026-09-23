`timescale 1ns/1ps
module counter (
    input wire clk,
    input wire btnC,
    input wire [15:0] sw,
    output wire [15:0] led
);
    reg [7:0] count = 0;
`ifdef INCLUDE_VIO
    wire [1:0] debug_control;
    vio_control_ip vio0 (.clk(clk), .probe_in0(count), .probe_out0(debug_control));
`else
    wire [1:0] debug_control = 2'b01;
`endif
    always @(posedge clk)
        if (btnC || debug_control[1]) count <= 0;
        else if (sw[0] && debug_control[0]) count <= count + 1'b1;
    assign led = {8'b0, count};
endmodule
