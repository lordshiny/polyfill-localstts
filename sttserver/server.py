import time, logging
from datetime import datetime
import threading, collections, queue, os, os.path
import stt
import numpy as np
import pyaudio
import wave
import webrtcvad
import scipy

import signal
import asyncio
import websockets
import json

logging.basicConfig(level=20)

class Audio(object):
    '''Streams raw audio from microphone. Data is received in a separate thread, and stored in a buffer, to be read from.'''

    FORMAT = pyaudio.paInt16
    # Network/VAD rate-space
    RATE_PROCESS = 16000
    CHANNELS = 1
    BLOCKS_PER_SECOND = 50

    def __init__(self, callback=None, device=None, input_rate=RATE_PROCESS, file=None):
        def proxy_callback(in_data, frame_count, time_info, status):
            #pylint: disable=unused-argument
            if self.chunk is not None:
                in_data = self.wf.readframes(self.chunk)
            callback(in_data)
            return (None, pyaudio.paContinue)
        if callback is None: callback = lambda in_data: self.buffer_queue.put(in_data)
        self.buffer_queue = queue.Queue()
        self.device = device
        self.input_rate = input_rate
        self.sample_rate = self.RATE_PROCESS
        self.block_size = int(self.RATE_PROCESS / float(self.BLOCKS_PER_SECOND))
        self.block_size_input = int(self.input_rate / float(self.BLOCKS_PER_SECOND))
        self.pa = pyaudio.PyAudio()

        kwargs = {
            'format': self.FORMAT,
            'channels': self.CHANNELS,
            'rate': self.input_rate,
            'input': True,
            'frames_per_buffer': self.block_size_input,
            'stream_callback': proxy_callback,
        }

        self.chunk = None
        # if not default device
        if self.device:
            kwargs['input_device_index'] = self.device
        elif file is not None:
            self.chunk = 320
            self.wf = wave.open(file, 'rb')

        self.stream = self.pa.open(**kwargs)
        self.stream.start_stream()

    def resample(self, data, input_rate):
        '''
        Microphone may not support our native processing sampling rate, so
        resample from input_rate to RATE_PROCESS here for webrtcvad and
        stt

        Args:
            data (binary): Input audio stream
            input_rate (int): Input audio rate to resample from
        '''
        data16 = np.frombuffer(buffer=data, dtype=np.int16)
        resample_size = int(len(data16) / self.input_rate * self.RATE_PROCESS)
        resample = scipy.signal.resample(data16, resample_size)
        resample16 = np.array(resample, dtype=np.int16)
        return resample16.tobytes()

    def read_resampled(self):
        '''Return a block of audio data resampled to 16000hz, blocking if necessary.'''
        return self.resample(data=self.buffer_queue.get(),
                             input_rate=self.input_rate)

    def read(self):
        '''Return a block of audio data, blocking if necessary.'''
        return self.buffer_queue.get()

    def destroy(self):
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()

    frame_duration_ms = property(lambda self: 1000 * self.block_size // self.sample_rate)


class VADAudio(Audio):
    '''Filter & segment audio with voice activity detection.'''

    def __init__(self, aggressiveness=3, device=None, input_rate=None, file=None):
        super().__init__(device=device, input_rate=input_rate, file=file)
        self.vad = webrtcvad.Vad(aggressiveness)

    def frame_generator(self):
        '''Generator that yields all audio frames from microphone.'''
        if self.input_rate == self.RATE_PROCESS:
            while True:
                yield self.read()
        else:
            while True:
                yield self.read_resampled()

    def vad_collector(self, padding_ms=300, ratio=0.75, frames=None):
        '''Generator that yields series of consecutive audio frames comprising each utterence, separated by yielding a single None.
            Determines voice activity by ratio of frames in padding_ms. Uses a buffer to include padding_ms prior to being triggered.
            Example: (frame, ..., frame, None, frame, ..., frame, None, ...)
                      |---utterence---|        |---utterence---|
        '''
        if frames is None: frames = self.frame_generator()
        num_padding_frames = padding_ms // self.frame_duration_ms
        ring_buffer = collections.deque(maxlen=num_padding_frames)
        triggered = False

        for frame in frames:
            if len(frame) < 640:
                return

            is_speech = self.vad.is_speech(frame, self.sample_rate)

            if not triggered:
                ring_buffer.append((frame, is_speech))
                num_voiced = len([f for f, speech in ring_buffer if speech])
                if num_voiced > ratio * ring_buffer.maxlen:
                    triggered = True
                    for f, s in ring_buffer:
                        yield f
                    ring_buffer.clear()

            else:
                yield frame
                ring_buffer.append((frame, is_speech))
                num_unvoiced = len([f for f, speech in ring_buffer if not speech])
                if num_unvoiced > ratio * ring_buffer.maxlen:
                    triggered = False
                    yield None
                    ring_buffer.clear()

async def send(websocket, message):
    try:
        await websocket.send(message)
    except websockets.ConnectionClosed:
        pass

def broadcast(message):
    for websocket in CLIENTS:
        asyncio.run(send(websocket, message))

CLIENTS = set()
async def handler(websocket):
    print('connected')
    CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        print('gone')
        CLIENTS.remove(websocket)

exit_event = threading.Event()

def audio_thread(ARGS):
    # Load STT model
    if os.path.isdir(ARGS.model):
        model_dir = ARGS.model
        ARGS.model = os.path.join(model_dir, 'output_graph.pb')
        ARGS.scorer = os.path.join(model_dir, ARGS.scorer)

    print('Initializing model...')
    logging.info('ARGS.model: %s', ARGS.model)
    model = stt.Model(ARGS.model)
    if ARGS.scorer:
        logging.info('ARGS.scorer: %s', ARGS.scorer)
        model.enableExternalScorer(ARGS.scorer)

    # Start audio with VAD
    vad_audio = VADAudio(aggressiveness=ARGS.vad_aggressiveness,
                         device=ARGS.device,
                         input_rate=ARGS.rate,
                         file=ARGS.file)
    print('Listening (ctrl-C to exit)...')
    frames = vad_audio.vad_collector()

    stream_context = model.createStream()
    last_decode = datetime.now()

    for frame in frames:
        if frame is not None:
            stream_context.feedAudioContent(np.frombuffer(frame, np.int16))
            now = datetime.now()
            if (now-last_decode).total_seconds() > .5:
                last_decode = datetime.now()
                text = stream_context.intermediateDecode()
                if len(text) > 0:
                    print(text)
                    words = text.split(' ')
                    items = []

                    if len(words) > 1:
                        items.append({ 'transcript': ' '.join(words[:-1]), 'confidence': 1.0 })
                    items.append({ 'transcript': words[-1], 'confidence': 0.5 })

                    broadcast(json.dumps({
                        'resultIndex': 0,
                        'results': [
                            {
                                'isFinal': False,
                                'items': items
                            }
                        ]
                    }))
            else:
                print('quiet')
        else:
            text = stream_context.finishStream()
            stream_context = model.createStream()
            if len(text) > 0:
                print(f'Recognized: {text}')
                broadcast(json.dumps({
                    'resultIndex': 0,
                    'results': [
                        {
                            'isFinal': True,
                            'items': [
                                { 'transcript': text, 'confidence': 1.0 }
                            ]
                        }
                    ]
                }))

        if exit_event.is_set():
            break


async def main():
    async with websockets.serve(handler, '127.0.0.1', 8765):
        print('listening')
        await asyncio.Future()


if __name__ == '__main__':
    DEFAULT_SAMPLE_RATE = 44100

    import argparse
    parser = argparse.ArgumentParser(description='Stream from microphone to STT using VAD')

    parser.add_argument('-v', '--vad_aggressiveness', type=int, default=3,
                        help='Set aggressiveness of VAD: an integer between 0 and 3, 0 being the least aggressive about filtering out non-speech, 3 the most aggressive. Default: 3')
    parser.add_argument('-f', '--file',
                        help='Read from .wav file instead of microphone')

    parser.add_argument('-m', '--model', required=True,
                        help='Path to the model (protocol buffer binary file, or entire directory containing all standard-named files for model)')
    parser.add_argument('-s', '--scorer',
                        help='Path to the external scorer file.')
    parser.add_argument('-d', '--device', type=int, default=None,
                        help='Device input index (Int) as listed by pyaudio.PyAudio.get_device_info_by_index(). If not provided, falls back to PyAudio.get_default_device().')
    parser.add_argument('-r', '--rate', type=int, default=DEFAULT_SAMPLE_RATE,
                        help=f'Input device sample rate. Default: {DEFAULT_SAMPLE_RATE}. Your device may require 44100.')
    ARGS = parser.parse_args()

    a_thread = threading.Thread(target=audio_thread, args=(ARGS,))
    a_thread.start()

    main_task = asyncio.ensure_future(main())
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        print('Ctrl-C pressed! Gracefully exiting')

    exit_event.set()
    a_thread.join()
