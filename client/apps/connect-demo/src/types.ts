export interface Config {
    apiUrl: string;
    connectUiUrl: string;
    apiKey: string;
    endUserId: string;
    allowedProviders: string;
}

export type Mode = "popup" | "redirect" | "embed";
export type Theme = "system" | "light" | "dark";

export interface LogEntry {
    id: number;
    time: string;
    level: "info" | "success" | "error";
    message: string;
    detail?: string;
}
