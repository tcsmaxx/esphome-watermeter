"""Validate production image HTTP options, including legacy callers."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
fixture=root/'tests/led_selection_requests.py';scope={'__file__':str(fixture)}
exec(fixture.read_text().split('with tempfile.TemporaryDirectory(')[0],scope)
source=scope['source'];source=source[:source.index('int main()')]+r'''
int main(){MeterSetup owner;owner.image_settings_.exposure=-1;
 auto legacy=form("ffffffffffffffff");assert(owner.parse_image_options_(&legacy)&&owner.pending_image_.exposure==-1);
 for(int wb=0;wb<=4;wb++)for(int value=-2;value<=2;value++){
  auto r=form("ffffffffffffffff");r.values["image_exposure"]={std::to_string(value)};r.values["image_contrast"]={std::to_string(value)};r.values["image_saturation"]={std::to_string(value)};r.values["image_white_balance"]={std::to_string(wb)};
  assert(owner.parse_options_(&r,true)&&owner.pending_image_.exposure==value&&owner.pending_image_.contrast==value&&owner.pending_image_.saturation==value&&owner.pending_image_.white_balance==wb);
 }
 auto valid=form("ffffffffffffffff");for(auto key:{"image_exposure","image_contrast","image_saturation","image_white_balance"})valid.values[key]={"0"};
 for(auto key:{"image_exposure","image_contrast","image_saturation","image_white_balance"}){
  for(auto value:{"","-3","3.0","1e0","256"," 1","-0","5"}){auto r=valid;r.values[key]={value};auto before=owner.pending_image_;assert(!owner.parse_options_(&r,true)&&r.status==400&&owner.pending_image_==before);}
  auto r=valid;r.values.erase(key);assert(!owner.parse_image_options_(&r)&&r.status==400);
 }
 std::cout<<"Image options passed: every valid level/mode, missing legacy group, incomplete groups, invalid numbers and no mutation on rejection\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-image-options-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
