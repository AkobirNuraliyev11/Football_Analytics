"""Local static preview with byte ranges for seeking existing match media."""
import argparse,functools,re,shutil
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.byte_count=None
        path=Path(self.translate_path(self.path))
        header=self.headers.get('Range')
        if not header or not path.is_file():return super().send_head()
        size=path.stat().st_size;match=re.fullmatch(r'bytes=(\d+)-(\d*)',header)
        if not match:
            self.send_error(416,'Unsupported range');return None
        start=int(match[1]);end=min(int(match[2]) if match[2] else size-1,size-1)
        if start>=size or end<start:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return None
        f=path.open('rb');f.seek(start);self.byte_count=end-start+1
        self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Content-Length',str(self.byte_count));self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.end_headers();return f
    def copyfile(self,source,outputfile):
        if self.byte_count is None:return shutil.copyfileobj(source,outputfile)
        remaining=self.byte_count
        while remaining:
            chunk=source.read(min(65536,remaining))
            if not chunk:break
            outputfile.write(chunk);remaining-=len(chunk)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--port',type=int,default=8013);a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),functools.partial(RangeHandler,directory=str(a.directory.resolve())))
    print(f'Local: http://127.0.0.1:{a.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
