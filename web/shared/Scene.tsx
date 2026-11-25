import { useEffect, useRef, type CSSProperties } from 'react';
import { KeyMark } from './KeyMark';

/** Lumini difuze, fixe în spatele paginii. Doar decor, ascunse cititoarelor de ecran. */
export function Backdrop() {
  return <div className="aurora" aria-hidden="true"><i /><i /><i /></div>;
}

const DEPTH = 9;

/**
 * Scenă 3D din CSS: o cheie extrudată (straturi suprapuse în adâncime), un inel în orbită și trei
 * documente de sticlă. Se înclină ușor după cursor; cu „mișcare redusă” rămâne nemișcată.
 */
export function HeroScene() {
  const scene = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = scene.current;
    if (!element || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let frame = 0;
    const move = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const x = event.clientX / window.innerWidth - 0.5;
        const y = event.clientY / window.innerHeight - 0.5;
        element.style.setProperty('--ry', `${(x * 26).toFixed(1)}deg`);
        element.style.setProperty('--rx', `${(-y * 20).toFixed(1)}deg`);
      });
    };
    window.addEventListener('pointermove', move, { passive: true });
    return () => { cancelAnimationFrame(frame); window.removeEventListener('pointermove', move); };
  }, []);
  return <div className="scene" ref={scene} aria-hidden="true">
    <div className="stage"><div className="float">
      <div className="ring" />
      <div className="key3d">
        {Array.from({ length: DEPTH }, (_, index) => <span key={index} className={index === 0 ? 'layer front' : 'layer'} style={{ '--i': index } as CSSProperties}><KeyMark /></span>)}
      </div>
      <div className="doc3d a">PDF</div><div className="doc3d b">PDF</div><div className="doc3d c">PDF</div>
    </div></div>
  </div>;
}
