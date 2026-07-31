import {existsSync, mkdirSync, readFileSync, readdirSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const {bundle} = require('@remotion/bundler');
const {renderMedia, selectComposition} = require('@remotion/renderer');

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../..');
const integralDir = path.join(repoRoot, 'remotion', 'integral');
const entryPoint = path.join(repoRoot, 'frontend', 'remotion', 'integral', 'index.ts');

const parseArgs = (argv) => {
  const args = {
    fps: 30,
    out: path.join(integralDir, 'out', 'integral-sequence.mp4'),
    dryRun: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    if (arg === '--fps') {
      args.fps = Number(argv[index + 1]);
      index += 1;
      continue;
    }

    if (arg === '--out') {
      args.out = path.resolve(process.cwd(), argv[index + 1]);
      index += 1;
      continue;
    }

    if (arg === '--dry-run') {
      args.dryRun = true;
      continue;
    }

    if (arg === '--help' || arg === '-h') {
      args.help = true;
      continue;
    }

    throw new Error(`Unknown argument: ${arg}`);
  }

  if (!Number.isFinite(args.fps) || args.fps <= 0) {
    throw new Error(`Invalid --fps value: ${args.fps}`);
  }

  return args;
};

const getNumberedFiles = () => {
  const files = readdirSync(integralDir);
  const jsNumbers = new Set();
  const wavNumbers = new Set();

  for (const file of files) {
    const match = /^(\d+)\.(js|wav)$/.exec(file);
    if (!match) {
      continue;
    }

    const number = Number(match[1]);
    if (match[2] === 'js') {
      jsNumbers.add(number);
    } else {
      wavNumbers.add(number);
    }
  }

  const numbers = [...jsNumbers].sort((a, b) => a - b);
  if (numbers.length === 0) {
    throw new Error(`No numbered .js files found in ${integralDir}`);
  }

  const missingAudio = numbers.filter((number) => !wavNumbers.has(number));
  if (missingAudio.length > 0) {
    throw new Error(`Missing matching .wav files for: ${missingAudio.join(', ')}`);
  }

  const extraAudio = [...wavNumbers]
    .sort((a, b) => a - b)
    .filter((number) => !jsNumbers.has(number));
  if (extraAudio.length > 0) {
    throw new Error(`Found .wav files without matching .js files: ${extraAudio.join(', ')}`);
  }

  return numbers;
};

const getWavDurationInSeconds = (audioPath) => {
  const buffer = readFileSync(audioPath);

  if (buffer.toString('ascii', 0, 4) !== 'RIFF' || buffer.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error(`Unsupported WAV file: ${audioPath}`);
  }

  let offset = 12;
  let byteRate = null;
  let dataSize = null;

  while (offset + 8 <= buffer.length) {
    const chunkId = buffer.toString('ascii', offset, offset + 4);
    const chunkSize = buffer.readUInt32LE(offset + 4);
    const chunkDataOffset = offset + 8;

    if (chunkId === 'fmt ') {
      byteRate = buffer.readUInt32LE(chunkDataOffset + 8);
    }

    if (chunkId === 'data') {
      dataSize = chunkSize;
    }

    offset = chunkDataOffset + chunkSize + (chunkSize % 2);
  }

  if (!byteRate || !dataSize) {
    throw new Error(`Could not read WAV duration from ${audioPath}`);
  }

  return dataSize / byteRate;
};

const getAudioFrames = (audioPath, fps) => {
  const durationInSeconds = getWavDurationInSeconds(audioPath);
  if (!Number.isFinite(durationInSeconds) || durationInSeconds <= 0) {
    throw new Error(`Invalid WAV duration for ${audioPath}: ${durationInSeconds}`);
  }

  return Math.ceil(durationInSeconds * fps);
};

const formatFrames = (frames, fps) => `${frames}f (${(frames / fps).toFixed(2)}s)`;

const main = async () => {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    console.log(
      [
        'Render remotion/integral/*.js + *.wav into one stitched MP4.',
        '',
        'Usage:',
        '  node frontend/scripts/render-integral.mjs [--out path] [--fps 30] [--dry-run]',
      ].join('\n'),
    );
    return;
  }

  if (!existsSync(entryPoint)) {
    throw new Error(`Remotion entry point not found: ${entryPoint}`);
  }

  const sceneNumbers = getNumberedFiles();
  const segments = sceneNumbers.map((id) => {
    const audioPath = path.join(integralDir, `${id}.wav`);
    return {
      id,
      audioFrames: getAudioFrames(audioPath, args.fps),
    };
  });

  console.log(`Detected ${segments.length} scene/audio pairs in ${integralDir}`);
  for (const segment of segments) {
    console.log(`  ${segment.id}: ${formatFrames(segment.audioFrames, args.fps)}`);
  }

  const inputProps = {segments};
  const serveUrl = await bundle({
    entryPoint,
    webpackOverride: (config) => config,
  });

  const composition = await selectComposition({
    serveUrl,
    id: 'IntegralSequence',
    inputProps,
  });

  console.log(
    `Composition duration: ${formatFrames(composition.durationInFrames, composition.fps)}`,
  );

  if (args.dryRun) {
    console.log('Dry run complete. Skipping render.');
    return;
  }

  mkdirSync(path.dirname(args.out), {recursive: true});

  let lastPercent = -1;
  await renderMedia({
    composition,
    serveUrl,
    codec: 'h264',
    audioCodec: 'aac',
    outputLocation: args.out,
    overwrite: true,
    inputProps,
    onProgress: ({progress}) => {
      const wholePercent = Math.floor(progress * 100);
      if (wholePercent === lastPercent) {
        return;
      }

      lastPercent = wholePercent;
      if (wholePercent % 5 === 0 || wholePercent === 100) {
        console.log(`Render progress: ${wholePercent}%`);
      }
    },
  });

  console.log(`Rendered ${args.out}`);
};

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
