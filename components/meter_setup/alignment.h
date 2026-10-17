#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>
namespace esphome::meter_setup {
constexpr int REF_SIDE=16, REF_PIXELS=REF_SIDE*REF_SIDE, SEARCH_RADIUS=20;
struct AlignmentReference {
  uint32_t version{1};
  uint16_t regions[2][4]{};
  uint8_t pixels[2][REF_PIXELS]{};
  uint8_t enabled{0}, ready{0};
  int16_t rotation_tenths{0};
};
struct AlignmentMatch { int dx{0},dy{0}; float score{-1}, uniqueness{0}; bool valid{false}; };
struct AlignmentTransform { float c{1},s{0},tx{0},ty{0}; bool valid{false}; };
// Inverse mapping for clockwise rotation, fitting the entire image into 640x480.
inline AlignmentTransform image_rotation(int16_t tenths) {
  const float a=tenths*0.00174532925199433f,c=std::cos(a),s=std::sin(a);
  const float scale=std::min(640.f/(std::abs(c)*640+std::abs(s)*480),480.f/(std::abs(s)*640+std::abs(c)*480));
  AlignmentTransform t;t.c=c/scale;t.s=-s/scale;
  t.tx=319.5f-t.c*319.5f+t.s*239.5f;t.ty=239.5f-t.s*319.5f-t.c*239.5f;t.valid=true;return t;
}
inline bool valid_reference_regions(const AlignmentReference &r) {
  if(r.version!=1 || r.enabled>1 || r.ready>1) return false;
  for(const auto &b:r.regions) if(b[0]>=b[2] || b[1]>=b[3] || b[2]>640 || b[3]>480 || b[2]-b[0]<16 || b[3]-b[1]<16 || b[2]-b[0]>96 || b[3]-b[1]>96) return false;
  const float dx=(int(r.regions[1][0])+r.regions[1][2]-r.regions[0][0]-r.regions[0][2])*0.5f;
  const float dy=(int(r.regions[1][1])+r.regions[1][3]-r.regions[0][1]-r.regions[0][3])*0.5f;
  return dx*dx+dy*dy>=80*80;
}
inline bool capture_reference(const uint8_t *gray, AlignmentReference &r,float *deviations=nullptr) {
  r.ready=0;
  if(deviations){deviations[0]=deviations[1]=0;}
  if(!gray || !valid_reference_regions(r)) return false;
  bool usable=true;
  for(int k=0;k<2;k++) {
    const auto &b=r.regions[k]; float sum=0,squares=0;
    for(int y=0;y<REF_SIDE;y++) for(int x=0;x<REF_SIDE;x++) {
      const int xx=b[0]+((2*x+1)*(b[2]-b[0]))/(2*REF_SIDE), yy=b[1]+((2*y+1)*(b[3]-b[1]))/(2*REF_SIDE);
      const uint8_t v=gray[yy*640+xx]; r.pixels[k][y*REF_SIDE+x]=v;sum+=v;squares+=float(v)*v;
    }
    const float variance=std::max(0.f,squares/REF_PIXELS-(sum/REF_PIXELS)*(sum/REF_PIXELS));
    if(deviations)deviations[k]=std::sqrt(variance);
    if(variance<64)usable=false; // At least 8 gray levels standard deviation.
  }
  r.ready=usable;return usable;
}
inline AlignmentMatch match_reference(const uint8_t *gray,const AlignmentReference &r,int k) {
  AlignmentMatch best;
  if(!gray || !r.ready || !valid_reference_regions(r) || k<0 || k>1) return best;
  const auto &b=r.regions[k]; float sum_t=0,sq_t=0;
  for(auto v:r.pixels[k]) {sum_t+=v;sq_t+=float(v)*v;}
  const float var_t=sq_t-sum_t*sum_t/REF_PIXELS;
  if(var_t<REF_PIXELS*64) return best;
  constexpr int span=SEARCH_RADIUS*2+1;
  std::vector<float> scores(span*span,-1);
  int offsets[REF_PIXELS];
  for(int y=0;y<REF_SIDE;y++) for(int x=0;x<REF_SIDE;x++) offsets[y*REF_SIDE+x]=(b[1]+((2*y+1)*(b[3]-b[1]))/(2*REF_SIDE))*640+b[0]+((2*x+1)*(b[2]-b[0]))/(2*REF_SIDE);
  for(int dy=-SEARCH_RADIUS;dy<=SEARCH_RADIUS;dy++) for(int dx=-SEARCH_RADIUS;dx<=SEARCH_RADIUS;dx++) {
    if(int(b[0])+dx<0 || int(b[1])+dy<0 || int(b[2])+dx>640 || int(b[3])+dy>480) continue;
    float sum=0,sq=0,cross=0;const int shift=dy*640+dx;
    for(int i=0;i<REF_PIXELS;i++) {const float v=gray[offsets[i]+shift];sum+=v;sq+=v*v;cross+=v*r.pixels[k][i];}
    const float var=sq-sum*sum/REF_PIXELS;
    if(var<REF_PIXELS*64) continue;
    const float score=(cross-sum*sum_t/REF_PIXELS)/std::sqrt(var*var_t);
    scores[(dy+SEARCH_RADIUS)*span+dx+SEARCH_RADIUS]=score;
    if(score>best.score) {best.score=score;best.dx=dx;best.dy=dy;}
  }
  float second=-1;
  for(int dy=-SEARCH_RADIUS;dy<=SEARCH_RADIUS;dy++) for(int dx=-SEARCH_RADIUS;dx<=SEARCH_RADIUS;dx++) if(std::abs(dx-best.dx)>2 || std::abs(dy-best.dy)>2) second=std::max(second,scores[(dy+SEARCH_RADIUS)*span+dx+SEARCH_RADIUS]);
  best.uniqueness=best.score-second;
  // A result on the search boundary could be a larger movement outside the window.
  best.valid=best.score>=0.85f && best.uniqueness>=0.05f && std::abs(best.dx)<SEARCH_RADIUS && std::abs(best.dy)<SEARCH_RADIUS;
  return best;
}
inline AlignmentTransform alignment_transform(const AlignmentReference &r,const AlignmentMatch &a,const AlignmentMatch &b) {
  AlignmentTransform t;if(!a.valid || !b.valid || !valid_reference_regions(r)) return t;
  const float ax=(r.regions[0][0]+r.regions[0][2])*0.5f, ay=(r.regions[0][1]+r.regions[0][3])*0.5f;
  const float bx=(r.regions[1][0]+r.regions[1][2])*0.5f, by=(r.regions[1][1]+r.regions[1][3])*0.5f;
  const float ux=bx-ax,uy=by-ay,vx=ux+b.dx-a.dx,vy=uy+b.dy-a.dy;
  const float old_len=std::hypot(ux,uy),new_len=std::hypot(vx,vy);
  if(new_len<1 || std::abs(new_len/old_len-1)>0.03f) return t;
  t.c=(ux*vx+uy*vy)/(old_len*new_len);t.s=(ux*vy-uy*vx)/(old_len*new_len);
  if(std::abs(std::atan2(t.s,t.c))>3.0f*3.14159265f/180.0f) return t;
  const float mx=(ax+bx)*0.5f,my=(ay+by)*0.5f;
  t.tx=mx+(a.dx+b.dx)*0.5f-t.c*mx+t.s*my;
  t.ty=my+(a.dy+b.dy)*0.5f-t.s*mx-t.c*my;t.valid=true;return t;
}
inline bool alignment_covers_box(const AlignmentTransform &t,const uint16_t b[4]) {
  if(!t.valid || b[0]>=b[2] || b[1]>=b[3]) return false;
  for(int x:{int(b[0]),int(b[2])-1}) for(int y:{int(b[1]),int(b[3])-1}) {
    const float xx=t.c*x-t.s*y+t.tx,yy=t.s*x+t.c*y+t.ty;
    if(xx<0 || yy<0 || xx>639 || yy>479) return false;
  }
  return true;
}
inline bool warp_rgb(const uint8_t *src,uint8_t *dst,const AlignmentTransform &t) {
  if(!src || !dst || src==dst || !t.valid) return false;
  for(int y=0;y<480;y++) for(int x=0;x<640;x++) {
    const float xx=t.c*x-t.s*y+t.tx,yy=t.s*x+t.c*y+t.ty;
    auto *out=dst+(y*640+x)*3;
    if(xx<0 || yy<0 || xx>639 || yy>479) {out[0]=out[1]=out[2]=0;continue;}
    const int x0=int(xx),y0=int(yy),x1=std::min(639,x0+1),y1=std::min(479,y0+1);
    const float fx=xx-x0,fy=yy-y0;
    for(int channel=0;channel<3;channel++) {
      const float top=src[(y0*640+x0)*3+channel]*(1-fx)+src[(y0*640+x1)*3+channel]*fx;
      const float bottom=src[(y1*640+x0)*3+channel]*(1-fx)+src[(y1*640+x1)*3+channel]*fx;
      out[channel]=uint8_t(top*(1-fy)+bottom*fy+0.5f);
    }
  }
  return true;
}
}
