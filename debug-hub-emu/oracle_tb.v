`timescale 1ps/1ps

// Local reverse-engineering oracle: this drives the post-route functional
// model made by scripts/export_debug_oracle.tcl. It is never used by the live
// virtual target and is not a bitstream-decoding side channel.
module oracle_tb;
  reg clk = 0;
  reg btnC = 0;
  reg [15:0] sw = 16'h0001;
  wire [15:0] led;
  reg tck = 0;
  reg tms = 1;
  reg tdi = 0;
  wire tdo;
  reg sampled;
  reg [2047:0] received;
  reg [36:0] last_iport = 37'h0;
  reg [16:0] last_oport = 17'h0;
  integer i;

  counter dut(.clk(clk), .btnC(btnC), .sw(sw), .led(led));
  JTAG_SIME2 #(.PART_NAME("7A35T")) jtag(.TDO(tdo), .TCK(tck), .TDI(tdi), .TMS(tms));
  always #5000 clk = ~clk;
  always @(posedge clk) begin
    if (dut.sl_iport0_o_0 !== last_iport || dut.sl_oport0_i_0 !== last_oport) begin
      $display("ORACLE_SLAVE time=%0t iport=%010x oport=%05x",
               $time, dut.sl_iport0_o_0, dut.sl_oport0_i_0);
      last_iport <= dut.sl_iport0_o_0;
      last_oport <= dut.sl_oport0_i_0;
    end
  end

  task jclock(input integer next_tms, input integer next_tdi);
    begin
      tms = next_tms; tdi = next_tdi;
      #45000 sampled = tdo;
      #5000 tck = 1;
      #50000 tck = 0;
    end
  endtask

  task tap_reset;
    begin
      repeat (6) jclock(1, 0);
      jclock(0, 0);
    end
  endtask

  task shift_ir(input [5:0] value);
    begin
      jclock(1, 0); jclock(1, 0); jclock(0, 0); jclock(0, 0);
      for (i = 0; i < 6; i = i + 1) jclock(i == 5, value[i]);
      jclock(1, 0); jclock(0, 0);
    end
  endtask

  task shift_dr(input integer width, input [127:0] value);
    begin
      received = 0;
      jclock(1, 0); jclock(0, 0); jclock(0, 0);
      for (i = 0; i < width; i = i + 1) begin
        jclock(i == width - 1, value[i]);
        received[i] = sampled;
      end
      jclock(1, 0); jclock(0, 0);
      $display("ORACLE IR_DR width=%0d tdi=%032x tdo=%032x", width, value, received);
    end
  endtask

  task replay_record(input integer record_index, input integer record_offset,
                     input integer width,
                     input [2047:0] record_tms, input [2047:0] record_tdi);
    begin
      received = 0;
      for (i = 0; i < width; i = i + 1) begin
        jclock(record_tms[i], record_tdi[i]);
        received[i] = sampled;
      end
      $display("ORACLE_RECORD index=%0d offset=%0d width=%0d tdo=%02048b",
               record_index, record_offset, width, received);
    end
  endtask

  initial begin
    #250000;
    // Raw XVC trace windows start after configuration with the server TAP in
    // Run-Test/Idle.  JTAG_SIME2's power-on TAP state is not guaranteed, so
    // establish the same starting state before replaying a bounded window.
    tap_reset;
`include "replay_calls.vh"
    #1000000;
    $display("DEBUG_ORACLE_DONE led=%04x", led);
    $finish;
  end
endmodule
