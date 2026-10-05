import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

interface PCB3DViewerProps {
  gltfUrl?: string
  boardWidth?: number
  boardHeight?: number
  className?: string
}

export function PCB3DViewer({
  gltfUrl,
  boardWidth = 100,
  boardHeight = 80,
  className = ''
}: PCB3DViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!mountRef.current) return

    // Scene setup
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x1a1a2e)

    // Camera
    const aspect = mountRef.current.clientWidth / mountRef.current.clientHeight
    const camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 1000)
    camera.position.set(0, 0, Math.max(boardWidth, boardHeight) * 1.5)

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight)
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    mountRef.current.appendChild(renderer.domElement)

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.enablePan = true
    controls.minDistance = 10
    controls.maxDistance = 500
    controls.target.set(boardWidth / 2, boardHeight / 2, 0)

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambientLight)

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8)
    dirLight1.position.set(100, 100, 100)
    dirLight1.castShadow = true
    dirLight1.shadow.mapSize.width = 2048
    dirLight1.shadow.mapSize.height = 2048
    dirLight1.shadow.camera.near = 0.5
    dirLight1.shadow.camera.far = 500
    dirLight1.shadow.camera.left = -100
    dirLight1.shadow.camera.right = 100
    dirLight1.shadow.camera.top = 100
    dirLight1.shadow.camera.bottom = -100
    scene.add(dirLight1)

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.4)
    dirLight2.position.set(-100, -100, 100)
    scene.add(dirLight2)

    // Ground plane
    const groundGeometry = new THREE.PlaneGeometry(boardWidth * 2, boardHeight * 2)
    const groundMaterial = new THREE.MeshStandardMaterial({
      color: 0x1a1a2e,
      roughness: 0.8,
      metalness: 0.1
    })
    const ground = new THREE.Mesh(groundGeometry, groundMaterial)
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -0.1
    ground.receiveShadow = true
    scene.add(ground)

    // Board outline helper
    const outlineGeometry = new THREE.BufferGeometry()
    const outlineVertices = new Float32Array([
      0, 0, 0,
      boardWidth, 0, 0,
      boardWidth, 0, 0,
      boardWidth, boardHeight, 0,
      boardWidth, boardHeight, 0,
      0, boardHeight, 0,
      0, boardHeight, 0,
      0, 0, 0
    ])
    outlineGeometry.setAttribute('position', new THREE.BufferAttribute(outlineVertices, 3))
    const outlineMaterial = new THREE.LineBasicMaterial({ color: 0x00d4aa, transparent: true, opacity: 0.5 })
    const outline = new THREE.LineSegments(outlineGeometry, outlineMaterial)
    scene.add(outline)

    // Load GLTF if provided
    let pcbModel: THREE.Group | null = null

    if (gltfUrl) {
      const loader = new GLTFLoader()
      loader.load(
        gltfUrl,
        (gltf) => {
          pcbModel = gltf.scene
          pcbModel.traverse((child) => {
            if (child instanceof THREE.Mesh) {
              child.castShadow = true
              child.receiveShadow = true
              // Enhance materials for PCB look
              if (child.material instanceof THREE.MeshStandardMaterial) {
                child.material.roughness = 0.3
                child.material.metalness = 0.7
              }
            }
          })
          
          // Center model
          const box = new THREE.Box3().setFromObject(pcbModel)
          const center = box.getCenter(new THREE.Vector3())
          pcbModel.position.sub(center)
          pcbModel.position.y = 0
          
          scene.add(pcbModel)
          setLoading(false)
        },
        (progress) => {
          console.log('Loading:', (progress.loaded / progress.total * 100) + '%')
        },
        (err) => {
          console.error('GLTF load error:', err)
          setError('Failed to load 3D model')
          setLoading(false)
        }
      )
    } else {
      // Create a placeholder board if no GLTF
      createPlaceholderBoard()
      setLoading(false)
    }

    function createPlaceholderBoard() {
      const boardGroup = new THREE.Group()
      
      // Board base
      const boardGeo = new THREE.BoxGeometry(boardWidth, boardHeight, 1.6)
      const boardMat = new THREE.MeshStandardMaterial({
        color: 0x1b5e20,
        roughness: 0.4,
        metalness: 0.1
      })
      const board = new THREE.Mesh(boardGeo, boardMat)
      board.position.z = 0.8
      board.castShadow = true
      board.receiveShadow = true
      boardGroup.add(board)

      // Some placeholder components
      const componentPositions = [
        { x: 25, y: 20, w: 10, h: 6, height: 3, color: 0x2c2c2c }, // IC
        { x: 60, y: 20, w: 5, h: 5, height: 2, color: 0x8b4513 },  // Capacitor
        { x: 75, y: 20, w: 5, h: 5, height: 2, color: 0x8b4513 },
        { x: 40, y: 50, w: 8, h: 4, height: 1.5, color: 0x8b4513 }, // Inductor
        { x: 80, y: 60, w: 3, h: 2, height: 1, color: 0xffd700 },   // LED
      ]

      componentPositions.forEach(comp => {
        const geo = new THREE.BoxGeometry(comp.w, comp.h, comp.height)
        const mat = new THREE.MeshStandardMaterial({ color: comp.color, roughness: 0.3, metalness: 0.7 })
        const mesh = new THREE.Mesh(geo, mat)
        mesh.position.set(comp.x, comp.y, comp.height / 2 + 0.8)
        mesh.castShadow = true
        mesh.receiveShadow = true
        boardGroup.add(mesh)
      })

      boardGroup.position.set(0, 0, 0)
      scene.add(boardGroup)
    }

    // Animation loop
    let animationId: number
    function animate() {
      animationId = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    // Handle resize
    function handleResize() {
      if (!mountRef.current) return
      const width = mountRef.current.clientWidth
      const height = mountRef.current.clientHeight
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height)
    }
    window.addEventListener('resize', handleResize)

    // Cleanup
    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', handleResize)
      renderer.dispose()
      if (pcbModel) {
        pcbModel.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.geometry.dispose()
            if (child.material instanceof THREE.Material) {
              child.material.dispose()
            }
          }
        })
      }
      groundGeometry.dispose()
      groundMaterial.dispose()
      outlineGeometry.dispose()
      outlineMaterial.dispose()
      mountRef.current?.removeChild(renderer.domElement)
    }
  }, [gltfUrl, boardWidth, boardHeight])

  if (error) {
    return (
      <div className={`pcb-3d-viewer ${className}`} ref={mountRef} style={{ width: '100%', height: '100%' }}>
        <div className="viewer-error">
          <h3>Failed to load 3D model</h3>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`pcb-3d-viewer ${className}`} ref={mountRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      {loading && (
        <div className="viewer-loading">
          <div className="spinner" />
          <p>Loading 3D model...</p>
        </div>
      )}
    </div>
  )
}

export default PCB3DViewer