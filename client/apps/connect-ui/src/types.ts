export interface CredentialFieldOption {
  value: string;
  label: string;
}

export interface CredentialField {
  key: string;
  label: string;
  type: "text" | "password" | "url" | "email" | "select";
  required: boolean;
  placeholder?: string;
  help_text?: string;
  options?: CredentialFieldOption[];
}

export interface CredentialSchema {
  fields: CredentialField[];
}

export interface Provider {
  key: string;
  name: string;
  auth_kind: "oauth2" | "basic" | "api_key";
  credential_schema: CredentialSchema | null;
}

export type ViewName =
  | "loading"
  | "provider_selection"
  | "oauth_init"
  | "credential_form"
  | "success"
  | "error";

export interface AppState {
  view: ViewName;
  token: string | null;
  openerOrigin: string | null;
  redirectUri: string | null;
  providers: Provider[];
  selectedProvider: Provider | null;
  connectionId: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  fieldErrors: Record<string, string>;
  formError: string | null;
  submitting: boolean;
}

export interface PostMessageSuccess {
  type: "omnidapter:success";
  connectionId: string;
  provider: string;
}

export interface PostMessageError {
  type: "omnidapter:error";
  code: string;
  message: string;
}

export interface PostMessageClose {
  type: "omnidapter:close";
}
