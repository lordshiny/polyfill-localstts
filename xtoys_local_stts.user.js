// ==UserScript==
// @name         XToys Local (S)TT(S)
// @namespace    https://github.com/lordshiny
// @version      0.8
// @description  Enable local TTS & STT
// @author       shiny
// @match        https://xtoys.app/
// @icon         https:/xtoys.app/favicon.ico
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    window.speechSynthesis.speak = async function(msg) {
        // Change the URL to match your TTS server
        let response = await fetch('http://127.0.0.1:5002/api/tts?text='+encodeURIComponent(msg.text)+'&speaker_id=&style_wav=&language_id=', {
            'method': 'GET',
            'mode': 'cors'
        });
        if(response.ok) {
            if(!window.speechAudioPlayer) {
                window.speechAudioPlayer = document.createElement('AUDIO');
            }
            window.speechAudioPlayer.src = URL.createObjectURL(await response.blob());
            window.speechAudioPlayer.play();
        }
    }

    class SpeechRecognition {
        constructor() {
            this.grammars = null;
            this.lang = null;
            this.continuous = false;
            this.interimResults = false;
            this.maxAlternatives = 1;
            this.isRecognizing = false;
            this.simulation = null;
            this.websocket = null;

            // Change the URL to match your STT WebSocket server
            this.websocket = new WebSocket('ws://127.0.0.1:8765');

            this.websocket.addEventListener('open', this.onWebsocketOpen_.bind(this));
            this.websocket.addEventListener('close', this.onWebsocketClose_.bind(this));
            this.websocket.addEventListener('error', this.onWebsocketError_.bind(this));
            this.websocket.addEventListener('message', this.onWebsocketMessage_.bind(this));

            // Event handlers stored in an object
            this.eventHandlers = {
                result: [],
            };
            // Event properties
            this.onresult = null;
        }

        start() {
            if (this.isRecognizing) return;

            // Dump all properties to the console
            console.debug('grammars:', this.grammars);
            console.debug('lang:', this.lang);
            console.debug('continuous:', this.continuous);
            console.debug('interimResults:', this.interimResults);
            console.debug('maxAlternatives:', this.maxAlternatives);

            this.isRecognizing = true;

            // I used this whilst testing without a STT-Engine
            /*
            this.simulation = setInterval(() => {
                const phrase = 'Simulated recognition result';
                const words = phrase.split(' ');
                for(var i = 0; i <= words.length; i++) {
                    let res = [];

                	if(i > 0) {
                        const itemConcat = [ { transcript: words.slice(0,i).join(' '), confidence: 1.0 } ];
                        itemConcat.isFinal = i != words.length-1;
                        res.push(itemConcat);
                    }


                    if(i < words.length) {
                        const itemPreview = [ { transcript: words[i], confidence: 0.5 } ];
                        itemPreview.isFinal = false;
                        res.push(itemPreview);
                    }

                    const results = {
                        resultIndex: res.length - 1,
                        results: res
                    };
                    this.triggerEvent_('result', results);
                    console.log('sending', JSON.stringify(results, null, 2));
                }
            }, 2000);
            */
        }

        stop() {
            this.isRecognizing = false;
            if(this.simulation) {
                clearInterval(this.simulation);
                this.simulation = null;
            }
            if(this.websocket) {
                 this.websocket.close();
                 this.websocket = null;
            }
        }

        abort() {
            this.stop();
        }

        addEventListener(eventType, handler) {
            if (this.eventHandlers[eventType]) {
                this.eventHandlers[eventType].push(handler);
            }
        }

        removeEventListener(eventType, handler) {
            if (this.eventHandlers[eventType]) {
                const index = this.eventHandlers[eventType].indexOf(handler);
                if (index !== -1) {
                    this.eventHandlers[eventType].splice(index, 1);
                }
            }
        }

        triggerEvent_(eventType, eventData) {
            if (this.eventHandlers[eventType]) {
                for (const handler of this.eventHandlers[eventType]) {
                    handler(eventData);
                }
            }
            if (eventType === 'result' && typeof this.onresult === 'function') {
                this.onresult(eventData);
            }
        }

        onWebsocketOpen_(event) {
            this.isRecognizing = true;
        }

        onWebsocketClose_(event) {
            if (event.wasClean) {
                console.log(`Connection closed cleanly, code=${event.code}, reason=${event.reason}`);
            } else {
                console.error('Connection died');
            }
            this.isRecognizing = false;
        }

        onWebsocketError_(event) {
            console.error(`WebSocket Error: ${event}`);
        }

        onWebsocketMessage_(event) {
            const message = event.data;
            console.log(`Received: ${message}`);

            // Example response from server:
            // {
            //     'resultIndex': 1,
            //     'results': [
            //         { isFinal: false, items: [ { transcript: 'this is a test', confidence: 1.0 } ] },
            //         { isFinal: false, items: [ { transcript: 'sentence', confidence: 0.5 } ] }
            //     ]
            // }

            try {
                let results = JSON.parse(message);
                // emulate "SpeechRecognitionResult"
                results.results = results.results.map(i => {
                    i.items.isFinal = i.isFinal;
                    return i.items;
                });
                this.triggerEvent_('result', results);
                console.log('sending', JSON.stringify(results, null, 2));
            } catch(ex) {
                console.error(`failed while processing message: ${ex.toString()}`);
            }
        }
    }
    window.SpeechRecognition = SpeechRecognition;
})();
