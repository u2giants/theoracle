export type NativeStaticManifest={schema_version:1;source_revision:string;assets:{path:string;sha256:string}[]};
export const STATIC_MANIFEST:string;
export function assertNativeEnvironment(env:NodeJS.ProcessEnv,requireToken?:boolean):void;
export function assertNativeSettings(env:NodeJS.ProcessEnv,settings:unknown):void;
export function readStaticManifest(path?:string):NativeStaticManifest;
export function nativeRequestAllowed(url:string,method:string,host:string|null,env:NodeJS.ProcessEnv,manifest:NativeStaticManifest):boolean;
export function nativeForwardingAllowed(host:string|null,proto:string|null,forwardedHost:string|null,forwarded:string|null,env:NodeJS.ProcessEnv):boolean;
export function assertNativeDatabaseURL(raw:string,settings:unknown):void;
