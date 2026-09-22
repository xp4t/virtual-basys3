`timescale 1ns/1ps
module counter (
    input wire clk,
    input wire btnC,
    input wire [15:0] sw,
    output wire [15:0] led
);
    reg [7:0] count = 0;
    always @(posedge clk)
        if (btnC) count <= 0;
        else if (sw[0]) count <= count + 1'b1;
    assign led = {8'b0, count};
endmodule
