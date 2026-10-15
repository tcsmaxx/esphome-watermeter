"""Serve the real setup HTML while rejecting large heap allocations.
Uses the production handler branch and ESPHome response classes. Run after code generation.
"""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
branch=cpp[cpp.index('  if(url=="/setup" && r->method()==HTTP_GET)'):cpp.index('  if(url=="/meter/status" && r->method()==HTTP_GET)')]
web=(root/'.esphome/build/wasserzaehler/src/esphome/components/web_server_idf/web_server_idf.h').read_text()
classes=web[web.index('class AsyncWebServerRequest;'):web.index('class AsyncWebServerRequest {')]
source=r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <new>
#include <string>
#include <utility>
#include <iostream>
bool limited=false;size_t largest=0;
void *operator new(size_t n){if(limited){if(n>largest)largest=n;if(n>1024)throw std::bad_alloc();}if(auto *p=malloc(n))return p;throw std::bad_alloc();}
void operator delete(void *p)noexcept{free(p);}void operator delete(void *p,size_t)noexcept{free(p);}
'''+f'#include "{root / "components/meter_setup/web_ui.h"}"\nusing namespace esphome::meter_setup;\n'+classes+r'''
constexpr int HTTP_GET=1;
class AsyncWebServerRequest {
 public:
 bool sent=false,no_store=false;const char *data=nullptr;size_t size=0;AsyncWebServerResponse *owned=nullptr;
 int method(){return HTTP_GET;}
 AsyncWebServerResponse *beginResponse(int,const char *,const std::string &s){return owned=new AsyncWebServerResponseContent(this,s);}
 AsyncWebServerResponse *beginResponse(int,const char *,const uint8_t *p,size_t n){return owned=new AsyncWebServerResponseProgmem(this,p,n);}
 void send(AsyncWebServerResponse *r){sent=true;data=r->get_content_data();size=r->get_content_size();}
 ~AsyncWebServerRequest(){delete owned;}
};
void AsyncWebServerResponse::addHeader(const char *name,const char *value){assert(strcmp(name,"Cache-Control")==0);assert(strcmp(value,"no-store")==0);const_cast<AsyncWebServerRequest*>(req_)->no_store=true;}
void serve(AsyncWebServerRequest *r,const std::string &url){
'''+branch+r'''
}
int main(){
 const std::string url="/setup";
 try{limited=true;for(int i=0;i<100;i++){AsyncWebServerRequest r;serve(&r,url);assert(r.sent&&r.no_store);assert(r.data==WEB_UI&&r.size==sizeof(WEB_UI)-1);assert(r.size>30000);assert(memcmp(r.data,"<!doctype html>",15)==0);}limited=false;}
 catch(const std::bad_alloc&){limited=false;std::cerr<<"Setup response tried to allocate "<<largest<<" heap bytes\n";return 1;}
 std::cout<<"Setup response passed: 100 requests, actual ESPHome response storage, no HTML copy, no allocations over 1024 bytes, no-store header\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-http-') as tmp:
 binary=str(Path(tmp)/'test')
 subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
