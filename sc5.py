import select
import socket
import struct
import logging
from socketserver import StreamRequestHandler, ThreadingTCPServer
SOCKS_VERSION = 5
class SocksProxy(StreamRequestHandler):
    def handle(self):
        print('Accepting connection from {}'.format(self.client_address))
        # 协商
        # 从客户端读取并解包两个字节的数据
        header = self.connection.recv(2)
        print('connection header {}'.format(header))
        version, nmethods = struct.unpack("!BB", header)
        # 设置socks5协议，METHODS字段的数目大于0
        assert version == SOCKS_VERSION
        assert nmethods > 0
        # 接受支持的方法
        methods = self.get_available_methods(nmethods)
        # 无需认证
        if 0 not in set(methods):
            self.server.close_request(self.request)
            return
        # 发送协商响应数据包
        send_pkg = struct.pack("!BB", SOCKS_VERSION, 0)
        print('connection send_pkg {}'.format(send_pkg))
        self.connection.sendall(send_pkg)
        # 请求
        recv_pkg = self.connection.recv(4)
        version, cmd, _, address_type = struct.unpack("!BBBB", recv_pkg)
        print('connection recv_pkg {}'.format(recv_pkg))
        assert version == SOCKS_VERSION
        if address_type == 1:  # IPv4
            address_pkg = self.connection.recv(4)
            address = socket.inet_ntoa(address_pkg)
            print('connection address_type == 1 address_pkg {}'.format(address_pkg))
            print('connection address {}'.format(address))
        elif address_type == 3:  # Domain name
            domain_length = self.connection.recv(1)[0]
            address = self.connection.recv(domain_length)
            print('connection address_type == 3 domain_length {} address {}'.format(domain_length, address))
            #address = socket.gethostbyname(address.decode("UTF-8"))  # 将域名转化为IP，这一行可以去掉
        elif address_type == 4: # IPv6
            addr_ip = self.connection.recv(16)
            address = socket.inet_ntop(socket.AF_INET6, addr_ip)
            print('connection address_type == 4 ipv6 addr_ip {} address {}'.format(addr_ip, address))
        else:
            self.server.close_request(self.request)
            return
        port = struct.unpack('!H', self.connection.recv(2))[0]
        print('connection port {}'.format(port))
        # 响应，只支持CONNECT请求
        try:
            if cmd == 1:  # CONNECT
                remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote.connect((address, port))
                bind_address = remote.getsockname()
                print('Connected to {} {}'.format(address, port))
            else:
                self.server.close_request(self.request)
            addr = struct.unpack("!I", socket.inet_aton(bind_address[0]))[0]
            port = bind_address[1]
            #reply = struct.pack("!BBBBIH", SOCKS_VERSION, 0, 0, address_type, addr, port)
            # 注意：按照标准协议，返回的应该是对应的address_type，但是实际测试发现，当address_type=3，也就是说是域名类型时，会出现卡死情况，但是将address_type该为1，则不管是IP类型和域名类型都能正常运行
            reply = struct.pack("!BBBBIH", SOCKS_VERSION, 0, 0, 1, addr, port)
        except Exception as err:
            logging.error(err)
            # 响应拒绝连接的错误
            reply = self.generate_failed_reply(address_type, 5)
        self.connection.sendall(reply)
        # 建立连接成功，开始交换数据
        if reply[1] == 0 and cmd == 1:
            self.exchange_loop(self.connection, remote)
        self.server.close_request(self.request)
    def get_available_methods(self, n):
        methods = []
        for i in range(n):
            methods.append(ord(self.connection.recv(1)))
        return methods
    def generate_failed_reply(self, address_type, error_number):
        return struct.pack("!BBBBIH", SOCKS_VERSION, error_number, 0, address_type, 0, 0)
    def exchange_loop(self, client, remote):
        while True:
            # 等待数据
            r, w, e = select.select([client, remote], [], [])
            if client in r:
                data = client.recv(4096)
                print("---------client: ")
                print(data)
                print("---------end: ")
                print("\n\n\n")
                if remote.send(data) <= 0:
                    break
            if remote in r:
                data = remote.recv(4096)
                print("=========remote: ")
                print(data)
                print("---------end: ")
                print("\n\n\n")
                if client.send(data) <= 0:
                    break
if __name__ == '__main__':
    # 使用socketserver库的多线程服务器ThreadingTCPServer启动代理
    with ThreadingTCPServer(('0.0.0.0', 9011), SocksProxy) as server:
        server.serve_forever()
