`timescale 1ps/1ps

// Development oracle top.  XSI exposes only the three JTAG inputs and TDO;
// the generated post-route design supplies the real Debug Hub and ILA.
module xsi_top(
  input wire tck,
  input wire tms,
  input wire tdi,
  output wire tdo
);
  reg clk = 0;
  reg btnC = 0;
  reg [15:0] sw = 16'h0001;
  wire [15:0] led;

  always #5000 clk = ~clk;
  counter dut(.clk(clk), .btnC(btnC), .sw(sw), .led(led));
  JTAG_SIME2 #(.PART_NAME("7A35T"))
    jtag(.TDO(tdo), .TCK(tck), .TDI(tdi), .TMS(tms));
endmodule
