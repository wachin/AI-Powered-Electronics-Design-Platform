/** @jsxImportSource react */
import { Circuit } from "tscircuit"
import {
  CircuitJsonToKicadSchConverter,
  CircuitJsonToKicadPcbConverter,
  CircuitJsonToKicadProConverter,
} from "circuit-json-to-kicad"
import { writeFileSync, mkdirSync, existsSync } from "fs"
import { join } from "path"

const OUTPUT_DIR = join(process.cwd(), "generated_design")

interface ConverterResult {
  success: boolean
  schematicPath?: string
  pcbPath?: string
  projectPath?: string
  errors: string[]
}

function ensureDir(dir: string): void {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true })
  }
}

async function circuitJsonToKicad(): Promise<ConverterResult> {
  console.log("=" .repeat(60))
  console.log("Circuit JSON → KiCad Converter")
  console.log("=" .repeat(60))

  const errors: string[] = []

  try {
    // Step 1: Create circuit using tscircuit
    console.log("\n📝 Step 1: Creating circuit with tscircuit...")

    const circuit = new Circuit()

    circuit.add(
      <board width="50mm" height="40mm">
        {/* Voltage Regulator Chip */}
        <chip
          name="U1"
          footprint="soic8"
          pinCount={8}
        />

        {/* Input Capacitor */}
        <capacitor
          name="C1"
          capacitance="10uF"
          footprint="0805"
        />

        {/* Output Capacitor */}
        <capacitor
          name="C2"
          capacitance="22uF"
          footprint="0805"
        />

        {/* LED Indicator */}
        <resistor name="R1" resistance="330" footprint="0805" />
        <led name="LED1" footprint="0803" />

        {/* Power Source - Using text for now */}
      </board>
    )

    await circuit.renderUntilSettled()
    console.log("✅ Circuit created and rendered")

    // Step 2: Get Circuit JSON
    console.log("\n📝 Step 2: Generating Circuit JSON...")

    const circuitJson = circuit.getCircuitJson()

    if (!circuitJson || circuitJson.length === 0) {
      throw new Error("Failed to generate Circuit JSON")
    }

    console.log(`✅ Circuit JSON generated (${circuitJson.length} elements)`)

    // Step 3: Convert to KiCad Schematic
    console.log("\n📝 Step 3: Converting to KiCad schematic...")

    const schConverter = new CircuitJsonToKicadSchConverter(circuitJson)
    schConverter.runUntilFinished()

    const kicadSchContent = schConverter.getOutputString()
    const schPath = join(OUTPUT_DIR, "design.kicad_sch")

    ensureDir(OUTPUT_DIR)
    writeFileSync(schPath, kicadSchContent)

    console.log(`✅ Schematic written to: ${schPath}`)

    // Step 4: Convert to KiCad PCB
    console.log("\n📝 Step 4: Converting to KiCad PCB...")

    const pcbConverter = new CircuitJsonToKicadPcbConverter(circuitJson)
    pcbConverter.runUntilFinished()

    const kicadPcbContent = pcbConverter.getOutputString()
    const pcbPath = join(OUTPUT_DIR, "design.kicad_pcb")

    writeFileSync(pcbPath, kicadPcbContent)

    console.log(`✅ PCB written to: ${pcbPath}`)

    // Step 5: Convert to KiCad Project
    console.log("\n📝 Step 5: Converting to KiCad project...")

    const proConverter = new CircuitJsonToKicadProConverter(circuitJson, {
      projectName: "design",
      schematicFilename: "design.kicad_sch",
      pcbFilename: "design.kicad_pcb",
    })

    proConverter.runUntilFinished()

    const kicadProContent = proConverter.getOutputString()
    const proPath = join(OUTPUT_DIR, "design.kicad_pro")

    writeFileSync(proPath, kicadProContent)

    console.log(`✅ Project written to: ${proPath}`)

    return {
      success: true,
      schematicPath: schPath,
      pcbPath: pcbPath,
      projectPath: proPath,
      errors: [],
    }

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    console.error(`❌ Error: ${errorMessage}`)
    errors.push(errorMessage)

    return {
      success: false,
      errors,
    }
  }
}

async function main(): Promise<void> {
  console.log("🚀 Starting Circuit JSON → KiCad conversion\n")

  const result = await circuitJsonToKicad()

  console.log("\n" + "=".repeat(60))
  if (result.success) {
    console.log("✅ Conversion completed successfully!")
    console.log(`\nGenerated files:`)
    console.log(`  📄 Schematic: ${result.schematicPath}`)
    console.log(`  📄 PCB:       ${result.pcbPath}`)
    console.log(`  📄 Project:   ${result.projectPath}`)
    console.log(`\nNext steps:`)
    console.log(`  1. Open project in KiCad`)
    console.log(`  2. Run ERC: kicad-cli sch erc ${result.schematicPath}`)
    console.log(`  3. Run DRC: kicad-cli pcb drc ${result.pcbPath}`)
  } else {
    console.log("❌ Conversion failed!")
    console.log(`\nErrors:`)
    result.errors.forEach(e => console.log(`  - ${e}`))
    process.exit(1)
  }
  console.log("=".repeat(60))
}

main()