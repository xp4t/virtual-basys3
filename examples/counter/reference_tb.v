`timescale 1ns/1ps
module reference_tb;
    reg clk = 0;
    reg btnC = 0;
    reg [15:0] sw = 0;
    wire [15:0] led;
    counter dut(.clk(clk), .btnC(btnC), .sw(sw), .led(led));
    integer output_file;
    integer cycle;
    initial begin
        output_file = $fopen("reference.csv", "w");
        $fdisplay(output_file, "cycle,reset,enable,led");
        for (cycle = 0; cycle < 1024; cycle = cycle + 1) begin
            clk = 0;
            btnC = (cycle < 2 || cycle == 257 || cycle == 700);
            sw[0] = !(cycle >= 20 && cycle < 31) && (cycle % 19 != 0);
            #5 clk = 1;
            #1 $fdisplay(output_file, "%0d,%0d,%0d,%0d", cycle, btnC, sw[0], led);
            #4;
        end
        $fclose(output_file);
        $display("REFERENCE_PASS: 1024 counter samples");
        $finish;
    end
endmodule
