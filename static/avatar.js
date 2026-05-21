import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';

// 他ファイル（main.js）から参照するグローバルバインド
window.currentVrm = undefined;
window.isSpeaking = false;

const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();

let width = container.clientWidth;
let height = container.clientHeight;

const camera = new THREE.PerspectiveCamera(28, width / height, 0.1, 20.0);
camera.position.set(0.0, 1.2, 3.0); 

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(width, height);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

const ambientLight = new THREE.AmbientLight(0xffeedd, 1.0); 
scene.add(ambientLight);
const directionalLight = new THREE.DirectionalLight(0xfffbea, 1.0); 
directionalLight.position.set(1.0, 1.0, 1.0).normalize();
scene.add(directionalLight);

const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

const vrmPath = './7151938431140058353.vrm'; 

loader.load(vrmPath, (gltf) => {
    const vrm = gltf.userData.vrm;
    scene.add(vrm.scene);
    window.currentVrm = vrm;
    vrm.scene.rotation.y = Math.PI; 
    vrm.scene.position.x = 0.0; 
    vrm.scene.scale.set(1.18, 1.18, 1.18); 
    vrm.scene.position.y = -0.15; 
    
    document.getElementById('system-status').innerText = "システム起動準備完了（スペースキーで起動）";
});

const clock = new THREE.Clock();
let blinkTimer = 0;
let nextBlinkTime = 3.0; 

function animate() {
    requestAnimationFrame(animate);
    const deltaTime = clock.getDelta();
    const elapsedTime = clock.getElapsedTime();
    const t = elapsedTime; 
    
    if (window.currentVrm) {
        window.currentVrm.update(deltaTime);

        const spine = window.currentVrm.humanoid.getNormalizedBoneNode('spine');
        if (spine) spine.rotation.x = Math.sin(t * 2.5) * 0.01 + 0.01;
        const head = window.currentVrm.humanoid.getNormalizedBoneNode('head');
        if (head) head.rotation.y = Math.sin(t * 0.5) * 0.02;
        
        const baseY = parseFloat(document.getElementById('param-vrm-y').value);
        window.currentVrm.scene.position.y = baseY + Math.sin(t * 2.5) * 0.005;

        blinkTimer += deltaTime;
        if (blinkTimer >= nextBlinkTime) {
            const blinkDuration = 0.2;
            const progress = blinkTimer - nextBlinkTime;
            if (progress < blinkDuration) {
                const blinkVal = Math.sin((progress / blinkDuration) * Math.PI);
                window.currentVrm.expressionManager.setValue('blink', blinkVal);
            } else {
                window.currentVrm.expressionManager.setValue('blink', 0);
                blinkTimer = 0;
                nextBlinkTime = 2.0 + Math.random() * 4.0;
            }
        }

        if (window.isSpeaking && window.currentVrm.expressionManager) {
            const mouthOpen = Math.sin(t * 15) * 0.4 + 0.4; 
            window.currentVrm.expressionManager.setValue('aa', mouthOpen);
        } else if (window.currentVrm.expressionManager) {
            window.currentVrm.expressionManager.setValue('aa', 0);
        }

        const leftUpperArm = window.currentVrm.humanoid.getNormalizedBoneNode('leftUpperArm');
        if (leftUpperArm) {
            leftUpperArm.rotation.z = 1.3 + Math.sin(t * 1.5) * 0.02 + Math.cos(t * 0.7) * 0.01;
            leftUpperArm.rotation.x = 0.1 + Math.sin(t * 0.9) * 0.015;
        }
        const rightUpperArm = window.currentVrm.humanoid.getNormalizedBoneNode('rightUpperArm');
        if (rightUpperArm) {
            rightUpperArm.rotation.z = -1.3 + Math.sin(t * 1.6) * 0.02 + Math.cos(t * 0.8) * 0.01;
            rightUpperArm.rotation.x = 0.1 + Math.sin(t * 1.0) * 0.015;
        }
        const leftLowerArm = window.currentVrm.humanoid.getNormalizedBoneNode('leftLowerArm');
        if (leftLowerArm) leftLowerArm.rotation.y = -1.0 + Math.cos(t * 1.3) * 0.03 + Math.sin(t * 0.6) * 0.015;
        const rightLowerArm = window.currentVrm.humanoid.getNormalizedBoneNode('rightLowerArm');
        if (rightLowerArm) rightLowerArm.rotation.y = 1.0 + Math.cos(t * 1.4) * 0.03 + Math.sin(t * 0.5) * 0.015;
    }
    renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
    width = container.clientWidth;
    height = container.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
});