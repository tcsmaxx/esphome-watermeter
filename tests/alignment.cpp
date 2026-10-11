// Portable production kernel: image movement, rejection and corrected crops.
#include "../components/meter_setup/alignment.h"
#include <cassert>
#include <iostream>
#include <random>
using namespace esphome::meter_setup;
std::vector<uint8_t> scene(){
  std::vector<uint8_t> out(640*480);std::mt19937 random(4567);
  // Smooth, non-periodic texture resembling fixed printed features.
  std::vector<float> coarse(81*61);for(auto &v:coarse)v=20+random()%210;
  for(int y=0;y<480;y++)for(int x=0;x<640;x++){
    const float fx=(x%8)/8.f,fy=(y%8)/8.f;const int i=(y/8)*81+x/8;
    out[y*640+x]=(coarse[i]*(1-fx)+coarse[i+1]*fx)*(1-fy)+(coarse[i+81]*(1-fx)+coarse[i+82]*fx)*fy;
  }return out;
}
std::vector<uint8_t> moved(const std::vector<uint8_t>&src,float angle,float dx,float dy){
  const float c=std::cos(angle),s=std::sin(angle),tx=320+dx-c*320+s*240,ty=240+dy-s*320-c*240;
  std::vector<uint8_t> rgb(src.size()*3),dst(rgb.size());for(size_t i=0;i<src.size();i++)rgb[i*3]=rgb[i*3+1]=rgb[i*3+2]=src[i];
  // Synthesize the physical camera motion using its inverse map.
  AlignmentTransform inverse{c,-s,-c*tx-s*ty,s*tx-c*ty,true};assert(warp_rgb(rgb.data(),dst.data(),inverse));
  std::vector<uint8_t> out(src.size());for(size_t i=0;i<out.size();i++)out[i]=dst[i*3];return out;
}
int main(){
  auto gray=scene();AlignmentReference refs;refs.enabled=1;
  uint16_t regions[2][4]={{120,210,152,242},{480,210,512,242}};std::memcpy(refs.regions,regions,sizeof(regions));assert(valid_reference_regions(refs));assert(capture_reference(gray.data(),refs));
  auto current=moved(gray,0,9,-6);for(auto &v:current)v=std::min(255,int(v)+20); // Illumination offset.
  auto a=match_reference(current.data(),refs,0),b=match_reference(current.data(),refs,1);
  assert(a.valid&&b.valid&&a.dx==9&&a.dy==-6&&b.dx==9&&b.dy==-6);auto t=alignment_transform(refs,a,b);assert(t.valid&&std::abs(t.tx-9)<.01&&std::abs(t.ty+6)<.01);
  std::vector<uint8_t> rgb(current.size()*3),corrected(rgb.size());for(size_t i=0;i<current.size();i++)rgb[i*3]=rgb[i*3+1]=rgb[i*3+2]=current[i];assert(warp_rgb(rgb.data(),corrected.data(),t));
  for(int y=120;y<160;y++)for(int x=273;x<512;x++)assert(std::abs(int(corrected[(y*640+x)*3])-gray[y*640+x]-20)<=1);
  for(float angle:{-2.f,2.f}){auto rotated=moved(gray,angle*3.14159265f/180,2,-1);a=match_reference(rotated.data(),refs,0);b=match_reference(rotated.data(),refs,1);std::cout<<"Rotation "<<angle<<" scores "<<a.score<<" / "<<b.score<<", uniqueness "<<a.uniqueness<<" / "<<b.uniqueness<<"\n";assert(a.valid&&b.valid);assert(alignment_transform(refs,a,b).valid);}
  auto far=moved(gray,0,27,0);assert(!match_reference(far.data(),refs,0).valid);
  auto edge=moved(gray,0,20,0);assert(!match_reference(edge.data(),refs,0).valid);
  std::vector<uint8_t> flat(640*480,100);AlignmentReference empty=refs;empty.ready=0;assert(!capture_reference(flat.data(),empty));assert(!match_reference(flat.data(),refs,0).valid);
  auto duplicate=gray;auto repeat_refs=refs;repeat_refs.regions[0][2]=136;assert(capture_reference(gray.data(),repeat_refs));for(int y=210;y<242;y++)for(int x=120;x<136;x++)duplicate[y*640+x+17]=gray[y*640+x];assert(!match_reference(duplicate.data(),repeat_refs,0).valid); // Two indistinguishable candidates.
  AlignmentMatch ma{0,0,1,1,true},mb{0,20,1,1,true};assert(!alignment_transform(refs,ma,mb).valid);mb={19,0,1,1,true};assert(!alignment_transform(refs,ma,mb).valid); // Rotation and scale guards.
  uint16_t inside[4]={273,116,301,155},outside[4]={630,116,640,155};t=AlignmentTransform{1,0,9,-6,true};assert(alignment_covers_box(t,inside));assert(!alignment_covers_box(t,outside));assert(!warp_rgb(rgb.data(),rgb.data(),t));
  AlignmentReference wrong=refs;wrong.regions[1][0]=140;wrong.regions[1][2]=172;assert(!valid_reference_regions(wrong));
  std::cout<<"Alignment tests passed: translation, rotation, brightness, pixel mapping, ambiguity/missing/flat references, limits and ROI bounds\n";
}
