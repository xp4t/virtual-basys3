#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cerrno>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "xsi_loader.h"

static bool read_exact(int fd, void *buffer, size_t size) {
  auto *out = static_cast<unsigned char *>(buffer);
  while (size) {
    ssize_t got = read(fd, out, size);
    if (got == 0) return false;
    if (got < 0) {
      if (errno == EINTR) continue;
      throw std::runtime_error(std::strerror(errno));
    }
    out += got;
    size -= static_cast<size_t>(got);
  }
  return true;
}

static void write_exact(int fd, const void *buffer, size_t size) {
  const auto *in = static_cast<const unsigned char *>(buffer);
  while (size) {
    ssize_t sent = write(fd, in, size);
    if (sent < 0) {
      if (errno == EINTR) continue;
      throw std::runtime_error(std::strerror(errno));
    }
    in += sent;
    size -= static_cast<size_t>(sent);
  }
}

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: xsi_bridge SOCKET\n";
    return 2;
  }
  const std::string socket_path = argv[1];
  if (socket_path.size() >= sizeof(sockaddr_un::sun_path)) {
    std::cerr << "socket path is too long\n";
    return 2;
  }

  try {
    Xsi::Loader sim("xsim.dir/debug_xsi/xsimk.so",
                    "libxv_simulator_kernel.so");
    s_xsi_setup_info setup;
    std::memset(&setup, 0, sizeof(setup));
    char log_name[] = "xsi-kernel.log";
    setup.logFileName = log_name;
    sim.open(&setup);

    const int tck_port = sim.get_port_number("tck");
    const int tms_port = sim.get_port_number("tms");
    const int tdi_port = sim.get_port_number("tdi");
    const int tdo_port = sim.get_port_number("tdo");
    if (tck_port < 0 || tms_port < 0 || tdi_port < 0 || tdo_port < 0)
      throw std::runtime_error("XSI JTAG port lookup failed");

    const s_xsi_vlog_logicval zero = {0, 0};
    const s_xsi_vlog_logicval one = {1, 0};
    sim.put_value(tck_port, &zero);
    sim.put_value(tms_port, &one);
    sim.put_value(tdi_port, &zero);
    sim.run(250000);

    // Put the primitive in a deterministic Run-Test/Idle state before the
    // first client arrives.  Vivado normally sends its own reset too, but the
    // bridge must not depend on a previous connection having left the TAP in
    // a friendly state.
    auto clock_bit = [&](bool tms_bit, bool tdi_bit) {
      sim.put_value(tms_port, tms_bit ? &one : &zero);
      sim.put_value(tdi_port, tdi_bit ? &one : &zero);
      sim.run(20000);
      sim.put_value(tck_port, &one);
      sim.run(20000);
      sim.put_value(tck_port, &zero);
    };
    for (int cycle = 0; cycle < 6; ++cycle) clock_bit(true, false);
    clock_bit(false, false);

    int listener = socket(AF_UNIX, SOCK_STREAM, 0);
    if (listener < 0) throw std::runtime_error(std::strerror(errno));
    sockaddr_un address;
    std::memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    std::strncpy(address.sun_path, socket_path.c_str(), sizeof(address.sun_path) - 1);
    unlink(socket_path.c_str());
    if (bind(listener, reinterpret_cast<sockaddr *>(&address), sizeof(address)) < 0)
      throw std::runtime_error(std::strerror(errno));
    if (listen(listener, 1) < 0) throw std::runtime_error(std::strerror(errno));
    std::cerr << "XSI Debug Hub oracle listening on " << socket_path << "\n";

    for (;;) {
      int client = accept(listener, nullptr, nullptr);
      if (client < 0) {
        if (errno == EINTR) continue;
        throw std::runtime_error(std::strerror(errno));
      }
      try {
        for (;;) {
          uint32_t count_le;
          if (!read_exact(client, &count_le, sizeof(count_le))) break;
          uint32_t count = le32toh(count_le);
          size_t size = (static_cast<size_t>(count) + 7) / 8;
          std::vector<unsigned char> tms(size), tdi(size), tdo(size, 0);
          if (!read_exact(client, tms.data(), size) ||
              !read_exact(client, tdi.data(), size)) break;
          for (uint32_t bit = 0; bit < count; ++bit) {
            bool tms_bit = (tms[bit / 8] >> (bit % 8)) & 1;
            bool tdi_bit = (tdi[bit / 8] >> (bit % 8)) & 1;
            sim.put_value(tms_port, tms_bit ? &one : &zero);
            sim.put_value(tdi_port, tdi_bit ? &one : &zero);
            // The fixture clock is 100 MHz. A 25 MHz JTAG clock leaves four
            // fabric cycles per bit for the hub's CDC synchronizers while
            // avoiding unnecessary gate-level simulation work.
            sim.run(15000);
            s_xsi_vlog_logicval sampled = {0, 0};
            sim.get_value(tdo_port, &sampled);
            if ((sampled.bVal & 1) == 0 && (sampled.aVal & 1))
              tdo[bit / 8] |= static_cast<unsigned char>(1u << (bit % 8));
            sim.run(5000);
            sim.put_value(tck_port, &one);
            sim.run(20000);
            sim.put_value(tck_port, &zero);
          }
          write_exact(client, tdo.data(), size);
        }
      } catch (const std::exception &error) {
        std::cerr << "client error: " << error.what() << "\n";
      }
      close(client);
    }
  } catch (const std::exception &error) {
    std::cerr << "xsi_bridge: " << error.what() << "\n";
    return 1;
  }
}
