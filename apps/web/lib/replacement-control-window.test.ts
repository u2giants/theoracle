import assert from 'node:assert/strict';
import { test } from 'node:test';
import { canonicalJson } from './replacement-server-binding';
import { captureControlWindow, controlWindowRemaining, readControlWindow, CONTROL_WINDOW_HEADER } from './replacement-control-window';

test('actual original capture is finite, immutable, thirty seconds and same clock domain',()=>{
  const window=captureControlWindow();assert.equal(window.wall_end-window.wall_start,30000);assert.equal(Object.isFrozen(window),true);assert.ok(controlWindowRemaining(window)<=30000);
  assert.equal(canonicalJson(readControlWindow(new Headers({[CONTROL_WINDOW_HEADER]:canonicalJson(window)}))),canonicalJson(window));
});
test('pure monotonic arithmetic consumes auth and handoff time without duration renewal',()=>{
  const window={wall_start:100000,wall_end:130000,mono_end:'30000000000',clock_domain:'1:100000'};
  assert.equal(controlWindowRemaining(window,{wall:110000,mono:10000000000n,domain:'1:100000'}),20000);
  assert.equal(controlWindowRemaining(window,{wall:120000,mono:20000000000n,domain:'1:100000'}),10000);
  assert.throws(()=>controlWindowRemaining(window,{wall:120000,mono:30000000000n,domain:'1:100000'}));
});
test('wall rollback, original expiry, foreign domain and future monotonic end refuse',()=>{
  const window={wall_start:100000,wall_end:130000,mono_end:'30000000000',clock_domain:'1:100000'};
  for(const now of [{wall:99999,mono:100n,domain:'1:100000'},{wall:130000,mono:100n,domain:'1:100000'},{wall:100001,mono:100n,domain:'2:100000'},{wall:100001,mono:-1n,domain:'1:100000'}])assert.throws(()=>controlWindowRemaining(window,now));
});
test('missing, duplicate, unknown, malformed, noncanonical, stale and foreign propagated context refuse',()=>{
  const window=captureControlWindow();
  assert.throws(()=>readControlWindow(new Headers()));
  for(const value of ['{}',canonicalJson({...window,actor:'never-authority'}),canonicalJson({...window,clock_domain:'999999999:1'}),canonicalJson({...window,wall_end:window.wall_end+1}),canonicalJson({...window,wall_start:true}),canonicalJson({...window,mono_end:'Infinity'}),'{ '+canonicalJson(window).slice(1),canonicalJson(window)+','+canonicalJson(window),'{"x":1,"x":2}'])assert.throws(()=>readControlWindow(new Headers({[CONTROL_WINDOW_HEADER]:value})));
});
