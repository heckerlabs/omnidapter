import { Config } from "./types";

export const STORAGE_KEY = "omnidapter_demo_config";

export const DEFAULT_CONFIG: Config = {
    apiUrl: "http://localhost:8000",
    connectUiUrl: "http://localhost:5123",
    apiKey: "",
    endUserId: "demo_user",
    allowedProviders: "",
};
