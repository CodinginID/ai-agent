export namespace settings {
	
	export class Settings {
	    gateway_url: string;
	    jarvis_mode: boolean;
	    tts_enabled: boolean;
	    whisper_bin: string;
	    piper_bin: string;
	    whisper_model_path: string;
	    piper_voice_path: string;
	
	    static createFrom(source: any = {}) {
	        return new Settings(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.gateway_url = source["gateway_url"];
	        this.jarvis_mode = source["jarvis_mode"];
	        this.tts_enabled = source["tts_enabled"];
	        this.whisper_bin = source["whisper_bin"];
	        this.piper_bin = source["piper_bin"];
	        this.whisper_model_path = source["whisper_model_path"];
	        this.piper_voice_path = source["piper_voice_path"];
	    }
	}

}

