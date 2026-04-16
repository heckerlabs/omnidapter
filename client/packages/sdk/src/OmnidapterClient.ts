import { Configuration, ConfigurationParameters } from './runtime';
import { CalendarApi, ConnectionsApi, LinkTokensApi, ProvidersApi } from './apis/index';

export class OmnidapterClient {
    readonly calendar: CalendarApi;
    readonly connections: ConnectionsApi;
    readonly linkTokens: LinkTokensApi;
    readonly providers: ProvidersApi;

    constructor(params: ConfigurationParameters) {
        const config = new Configuration(params);
        this.calendar = new CalendarApi(config);
        this.connections = new ConnectionsApi(config);
        this.linkTokens = new LinkTokensApi(config);
        this.providers = new ProvidersApi(config);
    }
}
