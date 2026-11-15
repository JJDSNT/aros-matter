# Resolver do sistema: nomes `.local` pelo mDNS — desenho (2026-11-15)

Contrato acordado em 2026-11-10: `aros-midihub/docs/mdns-integration-agreements.md`, seção "System
resolver" (item 4 da ordem de trabalho). Levantamento anterior: [2026-11-10-g12-mdns-integration.md](2026-11-10-g12-mdns-integration.md)
(lacuna S1). Este documento leva o contrato ao código do AROSTCP modular (master `c2a72c0d52`) e à
`dnssd.library` do #2264.

## O que o contrato exige

- **Nomes:** os terminados em `.local` (qualquer caixa, ponto final opcional) e os reversos das faixas
  link-local (`254.169.in-addr.arpa`, `8.e.f.ip6.arpa` a `b.e.f.ip6.arpa`), RFC 6762 §3 e §4. O
  `<host>.local` do próprio AROS também (o mdnsd o responde desde o D8).
- **Ordem:** literal ou nome localhost (RFC 6761 §6.3) → resposta da própria pilha, como hoje; depois
  o arquivo de hosts; depois `.local` só pelo mDNS (RFC 6762 §3), qualquer outro nome pelo DNS, como hoje.
- **Mecanismo:** o resolver abre a `dnssd.library` quando precisa (precedente: `miami.library` abre a
  `usergroup.library` sob demanda). Sem dependência de link. Sem a biblioteca ou sem o mdnsd, `.local`
  dá "host not found" e nada mais muda.
- **Sem ciclo:** o mdnsd nunca resolve `.local` pelo resolver do sistema.

## Onde fica no código

O resolver é o módulo `resolver` (`resolver.atcp`, `bsdsocket/conf/group-resolver.cfg`:
`STACK_RESOLVER_C`). Todas as consultas passam pela tabela dele (`api/resolver_module.c`):
`res_gethostbyname2`, `res_gethostbyaddr`, `res_gethostbyname_r`, `res_gethostbyaddr_r`,
`res_getaddrinfo`, `res_getnameinfo`. Os literais e o localhost já são respondidos antes, por
`resolver_literal()` (`api/resolver_stubs.c`, no núcleo).

**Um arquivo novo no grupo do resolver, `api/res_mdns.c`**, com uma única porta de entrada:

```c
/* name is .local (or a link-local reverse name: phase 2) */
int res_mdns_name(const char *name);
/* up to max addresses of name, family AF_INET, AF_INET6 or AF_UNSPEC,
 * each with its interface index; the count, or -1 with *h_errnop set */
int res_mdns_lookup(struct SocketBase *libPtr, const char *name, int family,
    struct res_mdns_addr *out, int max, int *h_errnop);
```

Ele abre a `dnssd.library`, chama `DNSSD_LookupAddressSyncA()` e fecha a biblioteca. Os seis pontos de
entrada chamam `res_mdns_name()` logo depois do arquivo de hosts e, quando o nome é `.local`, vão para
`res_mdns_lookup()` em vez do `res_search()`. O DNS e o cache do DNS (`dns_cache.c`) não veem `.local`:
o cache do mDNS é do mdnsd.

## Decisões

1. **Abrir e fechar a biblioteca a cada consulta**, sem base global. Não há estado compartilhado entre
   tasks, nada para fechar quando o módulo para, e o custo de um `OpenLibrary()` é desprezível perto de
   uma consulta mDNS (até 3 s). A `dnssd.library` fica residente depois do primeiro uso. Na compilação
   o módulo precisa só dos cabeçalhos da dnssd (`workbench-network-mdns-includes-dnssd` na metatarget);
   não liga contra nada.
2. **A API síncrona que já existe basta para nomes.** `DNSSD_LookupAddressSyncA()` usa sessão e porta
   próprias (qualquer task pode chamar), tem prazo (`DNSSD_Timeout`, padrão 3 s), Ctrl-C, devolve
   IPv4/IPv6 com o índice da interface e termina 250 ms depois do primeiro endereço. O resolver roda na
   task de quem chama, o que a API permite. Nada muda na biblioteca para a fase 1.
3. **A zona chega ao `getaddrinfo()`.** Hoje o `res_getaddrinfo()` passa pelo `hostent`, que não guarda
   zona. Para `.local`, ele chama `res_mdns_lookup()` direto e põe `sin6_scope_id` = `da_Interface` nos
   endereços link-local (`fe80::/10`), como o Readme §6.6 define a zona (RFC 4007). Os globais ficam com
   zona 0. É o único jeito de um `connect()` a `x.local` por link-local funcionar num host com duas
   interfaces.
4. **`gethostbyname*()` não carregam zona** (o `hostent` não tem onde). Para `AF_INET6`, os endereços
   globais vêm antes dos link-local, que vão sem zona: o Readme §6.6 já diz o que um link-local sem zona
   faz (a tabela de rotas escolhe o enlace). Documentado; quem precisa de zona usa `getaddrinfo()`.
5. **Prazo:** o padrão da biblioteca, 3 s (era o ponto em aberto do acordo). A consulta termina antes
   assim que há resposta (mais 250 ms para outros endereços). Sem mdnsd, `DNSSD_ERR_NOENGINE` volta na
   hora: nenhuma espera.
6. **Erros:** `NOTFOUND`, `TIMEOUT`, `NOENGINE`, biblioteca ausente → `HOST_NOT_FOUND` /
   `EAI_NONAME`; `CANCELLED` (Ctrl-C) → `EINTR` / `EAI_SYSTEM`, como uma consulta DNS interrompida;
   `NOMEM` → `NETDB_INTERNAL` + `ENOMEM` / `EAI_MEMORY`.
7. **Lista de busca:** um nome sem ponto, expandido pela lista de busca para `x.local` (um `DOMAIN local`
   na NetDB ou do DHCP), não vai ao DNS unicast: `res_search()` pula o domínio `local` (RFC 6762 §3, os
   nomes `.local` são do mDNS). Só o nome dado com `.local` vai ao mDNS; expandir para o mDNS fica fora,
   como no nss-mdns (`mdns4_minimal`).
8. **Parada do módulo:** já é recusada enquanto uma task está dentro de uma consulta (o slot conta);
   uma consulta mDNS conta igual a uma DNS.

## Fase 2: reverso link-local (`gethostbyaddr`, `getnameinfo`)

O acordo inclui os reversos de 169.254/16 e fe80::/10. A `dnssd.library` não tem consulta síncrona de
registro: seria um laço de espera no resolver, duplicando o de `DNSSD_LookupAddressSyncA()`. Proposta:
uma função genérica na biblioteca, `DNSSD_QueryRecordSyncA(name, rrtype, buffer, size, tags)` (o par
síncrono de `DNSSD_QueryRecordA()`), usada pelo resolver para o PTR e útil a outros clientes. Vai num PR
da `dnssd.library` depois do #2264; o resolver ganha o reverso em seguida. A fase 1 não depende dela.

## Testes

- `tests/mdns/` (hosted e m68k, contra o Avahi do host), um programa novo `resolvtest`:
  - `gethostbyname("<host Linux>.local")` → os IPv4 do host; `gethostbyname2(..., AF_INET6)` → globais
    antes de link-local;
  - `getaddrinfo(AF_UNSPEC)` → IPv4 e IPv6, com `sin6_scope_id` igual ao índice da interface do enlace
    nos link-local; `connect()` TCP a um serviço do host por esse endereço funciona com duas interfaces
    (TWO=1);
  - o nome do próprio AROS (`arosbox.local`);
  - um nome inexistente → `HOST_NOT_FOUND` em cerca de 3 s; sem mdnsd → na hora;
  - uma entrada no arquivo de hosts para um `.local` ganha do mDNS;
  - tcpdump na porta 53: nenhuma consulta `.local` ao DNS (nem pela lista de busca com `DOMAIN local`).
- `ping <host>.local` e `ssh`/um cliente qualquer por nome, como verificação de ponta a ponta.
- Suíte cunit do AROSTCP inteira (os testes do resolver existentes não podem mudar).
- m68k: delta de tamanho do `resolver.atcp`.

## Ordem e PRs

- Depende do #2264 (a `dnssd.library` está nele). Implementação no worktree da linha mDNS, sobre o ramo
  do #2264, e PR do AROSTCP depois do merge dele (um tópico: o resolver `.local`, fase 1, com bump).
- O B42 (troca de hostname em execução não chega ao mdnsd) mexe no `resolver.atcp`/núcleo, mas é outro
  tópico: PR separado.
- Fase 2 (reverso): PR da `dnssd.library` (`DNSSD_QueryRecordSyncA`) e depois o do resolver.
