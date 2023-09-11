# Local (S)TT(S) Polyfill Userscripts with Coqui

This repository includes userscripts that serve as polyfills for text-to-speech and speech-to-text in browsers that lack support (e.g. Firefox), as well as for privacy-minded users, as it connects to locally hosted [coqui](https://github.com/coqui-ai/) instances.

The scripts were originally designed for the XToys App, although they should be generic enough to be used with other sites, as they merely partially emulate the behaviour of the [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)..

Server scripts are written in Python and utilize Pipenv for managing dependencies. If you do not already have it installed, please follow the guide on their [website](https://pipenv.pypa.io/en/latest/installation/).

To install the dependencies, simply run `pipenv install` in the respective directories.

To install the Userscripts, I recommend using either [Violentmonkey](https://violentmonkey.github.io/) or [Tampermonkey](https://www.tampermonkey.net/).

# Local Text to Speech

The TTS implementation is a bridge to the [example coqui TTS server](https://github.com/coqui-ai/TTS/tree/dev/TTS/server) with CORS support patched in.

To run the server go into the TTS directory `cd ttsserver`.

If this is your first time you might want to take a look at the available models/voices.

```pipenv run python server.py --list_models```

Then run the server with your chosen model. If you have a GPU that supports CUDA you can add `--use_cuda true` for a faster runtime.

```pipenv run python server.py --model_name tts_models/en/ljspeech/tacotron2-DDC --use_cuda true```

By default the server runs on port `5002`, if you've changed this or it's running on a different machine you'll need to make appropriate changes in the userscript.

# Local Speech to Text

> **Warning**
> - Coqui STT is EOL! Some things may not work anymore and/or dependecies may cause problems.
> - The code for the SST server is anything but clean.. Beware of the duct tape 😅
> - At the moment, polyfill only works with continuous speech recognition.

Like with the TTS server, the STT server is also based on a coqui example. This time it's the [mic_vad_streaming](https://github.com/coqui-ai/STT-examples/blob/r1.0/mic_vad_streaming/mic_vad_streaming.py) example. It has been modified to include a websocket server that streams the recognised text back to the client. The recording of the audio is being done by the server using pyaudio.

To run the server go into the STT directory `cd sttserver`.

For STT to work, you first need a speech recognition model. You can find it on their [their Github](https://github.com/coqui-ai/STT-models/releases).

In this example we use the english models:

```
wget https://github.com/coqui-ai/STT-models/releases/download/english%2Fcoqui%2Fv1.0.0-huge-vocab/model.tflite
wget https://github.com/coqui-ai/STT-models/releases/download/english%2Fcoqui%2Fv1.0.0-huge-vocab/huge-vocabulary.scorer
```

Then simply run the server. Then just run the server. If you want to change the input device, you can use the `-d` flag.

```pipenv run python server.py --model "model.tflite" --scorer "huge-vocabulary.scorer"```

By default the server runs on port `8765`, if you've changed this or it's running on a different machine you'll need to make appropriate changes in the userscript.
