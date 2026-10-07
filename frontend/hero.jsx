import React, {Component, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {useFrame, useThree} from '@react-three/fiber';
import {ShaderGradient, ShaderGradientCanvas} from '@shadergradient/react';

class EffectBoundary extends Component {
  state = {failed: false};
  static getDerivedStateFromError() { return {failed: true}; }
  componentDidCatch() { this.props.onFailure(); }
  render() { return this.state.failed ? null : this.props.children; }
}
function FramePolicy({active, host}) {
  const setFrameloop = useThree(s => s.setFrameloop);
  const invalidate = useThree(s => s.invalidate);
  const canvas = useThree(s => s.gl.domElement);
  const ready = useRef(false);
  useEffect(() => {
    setFrameloop(active ? 'always' : 'demand'); invalidate();
    host.dataset.rendering = active ? 'active' : 'paused';
  }, [active, setFrameloop, invalidate, host]);
  useEffect(() => {
    const lost = event => { event.preventDefault(); host.dataset.renderer = 'fallback'; setFrameloop('never'); };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [canvas, host, setFrameloop]);
  useFrame(() => { if (!ready.current) { ready.current = true; host.dataset.renderer = 'shader'; } });
  return null;
}
export function mountHero(host, initial) {
  const root = createRoot(host.querySelector('.shader-mount'));
  let disposed = false;
  function update({active, dark}) {
    if (disposed) return;
    root.render(<EffectBoundary onFailure={() => { host.dataset.renderer = 'fallback'; }}>
      <ShaderGradientCanvas pixelDensity={1} pointerEvents="none" lazyLoad={false} powerPreference="low-power">
        <ShaderGradient type="waterPlane" animate={active ? 'on' : 'off'}
          uSpeed={.12} uStrength={2.2} uDensity={1.3} uFrequency={0} uAmplitude={0}
          cAzimuthAngle={180} cPolarAngle={115} cDistance={3.3} cameraZoom={1}
          positionY={.2} rotationZ={220} lightType="3d" brightness={dark ? .85 : 1.2}
          color1={dark ? '#986048' : '#d58b62'} color2={dark ? '#342831' : '#f1d4b5'}
          color3={dark ? '#1d2337' : '#bfc7de'} grain="off" reflection={.05}
          enableTransition={false} enableCameraUpdate={false}/>
        <FramePolicy active={active} host={host}/>
      </ShaderGradientCanvas>
    </EffectBoundary>);
  }
  update(initial);
  return {update, dispose() { disposed = true; root.unmount(); }};
}
