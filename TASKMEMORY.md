# Bendango Task Memory

> Source of truth for the evolution of Bendango.
>
> This file must be updated whenever a meaningful architectural decision, milestone,
> migration, feature, test, or change of direction is made. New work should align
> with this roadmap unless the product direction is explicitly changed.

## 1. Product Vision

Bendango is not only a price-comparison engine.

The long-term goal is to make it easy for **any business or independent seller** to
publish what they sell or offer, even if they do not own a website.

Typical users include:

- WhatsApp-status sellers
- Independent merchants
- Boutiques
- Pharmacies
- Supermarkets
- Restaurants
- Hotels and accommodation providers
- Beauty salons
- Electronics stores
- Fashion businesses
- Food sellers
- Service providers
- Transport businesses
- Real-estate businesses
- Health businesses
- Other local or online businesses

Bendango should let customers discover, compare, and contact these businesses while
also enriching results with external web merchants and social-platform discovery.

The strategic search order should become:

1. Bendango first-party business/offers database
2. External merchant websites
3. Social networks and discovery sources
4. Unified ranking / comparison / presentation

As the Bendango business catalog grows, dependency on external scraping should
decrease.

---

## 2. Product Principles

### 2.1 Universal business model

Do not model every professional as only a `Retailer`.

Use a broader **Business** concept that can represent:

- Store
- Seller
- Pharmacy
- Hotel
- Restaurant
- Service provider
- Transport provider
- Real estate
- Health provider
- Other establishment/business types

`Retailer` remains useful internally for product price comparison, but it must not
be the only representation of a professional account.

### 2.2 Universal offer model

Do not force every listing to be a physical `Product + PriceListing`.

Introduce a broader **Offer** concept capable of representing:

- Physical product
- Service
- Hotel room / accommodation
- Restaurant/menu offer
- Health/pharmacy offer
- Transport offer
- Real-estate offer
- Other offer types

For physical comparable goods, keep using/coupling to `Product` and
`PriceListing` so the existing price-comparison engine remains useful.

### 2.3 WhatsApp-first publishing

A seller who currently sells only through WhatsApp Status must be able to publish
on Bendango without needing a website.

Minimum quick-publish fields:

- Photo
- Offer/product name
- Price
- Currency
- WhatsApp/contact
- Availability

A sale URL must be optional.

### 2.4 Progressive complexity

Provide two publishing modes:

**Quick publish**

- Photo
- Name/title
- Price
- WhatsApp/contact
- Publish

**Advanced publish**

- Brand/model
- SKU/EAN
- Category
- Description
- Attributes
- Stock/availability
- Price unit
- External sale URL
- Social links
- Additional media

### 2.5 Trust and verification

Business verification must be progressive rather than binary.

Planned levels:

- Unverified
- Identity verified
- Business verified
- Bendango partner

Potential verification dimensions:

- Phone verified
- Email verified
- Address verified
- Documents verified

---

## 3. Current Implemented Foundation

The following features already exist and should be preserved:

### Search and comparison

- `SearchRun` asynchronous searches
- Market-specific search
- GLOBAL fallback
- External web merchant discovery
- Social/discovery sources
- Price normalization
- Product matching
- Variant conflict protection
- Merchant deduplication
- Search history
- Search detail pages
- Search result polling and finalization
- Anonymous visitors: one free search per session
- Authenticated users: searches linked to their account

### Accounts

- User signup
- Login/logout
- Personal search history
- User-owned SearchRuns
- Access isolation between users

### Pro/business account workflow

- Business account request
- Admin approval/rejection
- BusinessProfile activation
- BusinessProfile revocation
- Pro dashboard
- Editable business profile

### Pro catalog foundation

- BusinessProfile linked to a Retailer
- Product creation/editing
- PriceListing creation/editing
- Stock status
- Price/currency
- Image URL
- Sale URL
- Activation/deactivation
- Pro offers can participate in Bendango cached product search
- Business market code

This catalog implementation is a foundation only. It must evolve into the more
general Business + Offer architecture below.

---

## 4. Target Architecture

### 4.1 Core relationship

```text
User
  |
  +-- SearchRuns
  |
  +-- Business memberships
          |
          v
       Business
          |
          +-- Profile / identity
          +-- Locations
          +-- Contacts
          +-- Social links
          +-- Verification
          +-- Members / roles
          |
          +-- Offers
                |
                +-- Product offer
                +-- Service offer
                +-- Accommodation offer
                +-- Restaurant/menu offer
                +-- Health/pharmacy offer
                +-- Transport offer
                +-- Real-estate offer
                +-- Other
```

### 4.2 Business

The future Business entity/profile should support:

- Name
- Slug
- Business type/category
- Description
- Logo
- Cover image
- Country
- Market code
- City
- Address
- Latitude/longitude later if needed
- Phone
- WhatsApp
- Email
- Website (optional)
- Facebook
- Instagram
- TikTok
- Other social links
- Opening hours
- Verification level
- Verification flags
- Public/active state
- Created/updated timestamps

Business categories should be data-driven/extensible rather than hard-coded forever.

### 4.3 Offer

Common fields:

- Business
- Offer type
- Title
- Slug
- Description
- Price
- Currency
- Price unit
- Primary image
- Additional media
- Availability
- Active/public state
- Market/location
- Contact method
- WhatsApp contact
- External sale URL (optional)
- Category
- Structured attributes JSON
- Created/updated timestamps

Example attributes:

**Phone**

```json
{
  "brand": "Samsung",
  "model": "Galaxy A56",
  "ram": "8GB",
  "storage": "256GB"
}
```

**Hotel**

```json
{
  "room_type": "Standard",
  "capacity": 2,
  "breakfast": true,
  "price_unit": "night"
}
```

**Service**

```json
{
  "service_duration": "1h30",
  "appointment_required": true
}
```

---

## 5. Public Experience

### 5.1 Public Business page

Target route:

```text
/business/<slug>/
```

Should show:

- Business identity
- Verification badge
- Location
- Contact
- WhatsApp button
- Social links
- Opening hours
- Active offers
- Categories
- Search/filter within business

### 5.2 Public Offer page

Target route:

```text
/offer/<slug>/
```

Should show:

- Media
- Title
- Price
- Availability
- Business
- Verification
- Description
- Attributes
- Contact / WhatsApp
- External sale URL if present
- Share action
- Related/comparable offers

These pages should be easy to share from WhatsApp, Facebook, TikTok, Instagram,
and other channels.

---

## 6. Search Evolution

The search engine should become first-party-first.

Target flow:

```text
User query
   |
   v
Bendango Offer database
   |
   +-- matching first-party offers
   |
   v
External merchant search
   |
   v
Social/discovery search
   |
   v
Merge + normalize + rank
   |
   v
Results
```

### 6.1 Product comparison

For truly comparable products, Bendango should continue to calculate:

- Best price
- Average price
- Savings
- Availability
- Merchant/business trust
- Market relevance
- Price history

### 6.2 Services/hotel/non-product ranking

Do not rank non-product offers only by lowest price.

Use relevant dimensions such as:

- Price
- Availability
- Location
- Offer type
- Business verification
- User-selected criteria
- Quality signals

---

## 7. Business Dashboard Target

```text
Business Dashboard

Overview
├── Active offers
├── Views
├── WhatsApp clicks
├── Search appearances
└── Recent activity

Offers
├── Quick publish
├── Advanced publish
├── Edit
├── Disable
└── Duplicate

Business profile
├── Logo
├── Name
├── Category/type
├── Address
├── WhatsApp
├── Phone
├── Social networks
└── Opening hours

Analytics
├── Views
├── Contact clicks
├── Popular offers
├── Search appearances
└── Price positioning
```

---

## 8. Multi-user Business Management

A Business should eventually support multiple users.

Suggested roles:

- Owner
- Admin/manager
- Catalog editor
- Analyst/read-only

A single user may eventually belong to multiple businesses.

Do not permanently lock the architecture to `User -> OneToOne BusinessProfile`.

The current OneToOne relationship is transitional and should be migrated carefully
when business memberships are introduced.

---

## 9. Import and Publishing Channels

Planned publishing methods:

- Manual quick publish
- Manual advanced publish
- CSV import
- Excel import
- API
- Existing website/catalog import
- Potential assisted social/WhatsApp catalog import later

Never require a website for a Business or Offer.

---

## 10. Analytics

Future tracking should include:

- Business page views
- Offer page views
- WhatsApp clicks
- Phone clicks
- External-site clicks
- Search impressions
- Search clicks
- Popular offers
- Price competitiveness
- Conversion-oriented events where measurable

Analytics must be scoped to the owning business and must not leak another
business's private metrics.

---

## 11. Monetization — Later Phase

Do not prioritize monetization before the marketplace/catalog/search loop works well.

Possible future models:

- Premium business account
- Sponsored offers
- Featured businesses
- Advanced analytics
- Catalog automation/import tools
- Promotional campaigns

Sponsored content must remain distinguishable from organic ranking.

---

## 12. Delivery Roadmap

### Phase 0 — Foundation already completed

- [x] SearchRun architecture
- [x] Market-aware search
- [x] Merchant scraping
- [x] Social discovery
- [x] User signup/login
- [x] Personal history
- [x] One anonymous trial search per session
- [x] Pro-account request
- [x] Admin approval/rejection
- [x] Pro dashboard
- [x] Initial Product/PriceListing Pro catalog

### Phase 1 — Generalize the Business model

Implementation note: core model/public storefront work is implemented in the repository and is awaiting local migration/test validation before Phase 1 is considered operationally closed.

- [x] Add data-driven BusinessCategory
- [x] Add business slug
- [x] Add city
- [x] Add WhatsApp
- [x] Add public email
- [x] Add Facebook
- [x] Add Instagram
- [x] Add TikTok
- [x] Add opening hours data field
- [x] Add verification level
- [x] Add verification flags
- [x] Add public/active status
- [x] Keep website optional for Business profiles
- [x] Add public Business page at /business/<slug>/
- [x] Preserve compatibility with existing BusinessProfile rows via migration/backfill
- [x] Add migrations and regression tests

### Phase 2 — General Offer model

- [ ] Introduce Offer
- [ ] Add offer types
- [ ] Add offer slug
- [ ] Make external sale URL optional
- [ ] Add WhatsApp/contact CTA
- [ ] Add attributes JSON
- [ ] Add price unit
- [ ] Add location/market fields
- [ ] Add active/public state
- [ ] Add primary image/media model
- [ ] Link product offers to canonical Product when appropriate
- [ ] Keep PriceListing bridge for price-comparable goods
- [ ] Migrate existing Pro catalog safely
- [ ] Add isolation/security tests

### Phase 3 — Quick publishing

- [ ] Quick publish UI
- [ ] Photo
- [ ] Title
- [ ] Price
- [ ] Currency
- [ ] WhatsApp/contact
- [ ] Availability
- [ ] Publish in under one minute
- [ ] Advanced publish option

### Phase 4 — Public storefronts

- [ ] Public Business route
- [ ] Public Business page
- [ ] Public Offer route
- [ ] Public Offer page
- [ ] Shareable metadata
- [ ] WhatsApp CTA
- [ ] Phone CTA
- [ ] External-site CTA
- [ ] Business search/filter
- [ ] Related offers

### Phase 5 — Bendango-first search

- [ ] Search local Bendango offers before external web
- [ ] Market-aware first-party matching
- [ ] Merge internal + external + social results
- [ ] Deduplicate comparable offers
- [ ] Preserve trusted source labels
- [ ] Avoid treating social discovery as verified merchant pricing
- [ ] Product comparison uses canonical Product matching
- [ ] Non-product offers use appropriate ranking

### Phase 6 — Analytics

- [ ] Track offer views
- [ ] Track business views
- [ ] Track WhatsApp clicks
- [ ] Track phone clicks
- [ ] Track external-sale clicks
- [ ] Track search impressions
- [ ] Business analytics dashboard

### Phase 7 — Multi-user businesses

- [ ] BusinessMembership
- [ ] Owner role
- [ ] Manager role
- [ ] Catalog editor role
- [ ] Read-only/analyst role
- [ ] User can own/join multiple businesses
- [ ] Migrate away from permanent User OneToOne BusinessProfile assumption

### Phase 8 — Imports and automation

- [ ] CSV import
- [ ] Excel import
- [ ] API publishing
- [ ] Website catalog import
- [ ] Assisted social catalog import exploration

### Phase 9 — Monetization

- [ ] Premium business plans
- [ ] Sponsored offers
- [ ] Featured businesses
- [ ] Advanced analytics
- [ ] Promotional tools

---

## 13. Immediate Next Tasks

The next implementation sequence should be:

1. Finish validating the current Pro catalog migration/tests.
2. Start Phase 1: generalize BusinessProfile without breaking existing rows.
3. Add BusinessCategory and verification model/fields.
4. Add WhatsApp/social/location/public fields.
5. Add slug + public Business page.
6. Then introduce the general Offer model.
7. Migrate the existing Pro Product/PriceListing catalog into the Offer architecture
   while preserving comparison functionality.

---

## 14. Engineering Rules

Every roadmap implementation should follow these rules:

- Preserve existing data with migrations.
- Do not break current SearchRun behavior.
- Do not break existing Product/PriceListing comparison.
- Add regression tests for each change.
- Protect business ownership boundaries.
- Never let one business edit another business's offers.
- Prefer reversible migrations.
- Avoid duplicated business/product systems.
- Keep first-party Bendango offers distinguishable from externally scraped offers.
- Keep social/discovery results distinguishable from verified offers.
- Keep market/currency normalization behavior.
- Keep anonymous one-search trial behavior unless product direction changes.
- Update this TASKMEMORY.md after each meaningful milestone.

---

## 15. Current Status

Current milestone:

**Phase 2 implementation — General Offer model**

Phase 1 is functionally complete and validated by migration + test suite.

Implemented in this milestone:

- BusinessCategory with seeded extensible categories
- Public business slug
- City and market-aware profile
- WhatsApp and public contact channels
- Facebook / Instagram / TikTok links
- Cover image and opening-hours data
- Progressive verification levels and verification flags
- Public/active visibility controls
- Public storefront at `/business/<slug>/`
- Existing BusinessProfile migration/backfill
- Public storefront regression tests

Phase 1 validation:

- [x] Django system checks pass
- [x] Migration 0016 applied
- [x] Migration 0017 applied after PostgreSQL slug-index fix
- [x] Full suite passes: 214 tests, 1 skipped
- [ ] Smoke-test an approved Business public page in the browser

Validation note:
- 0017 initially failed on PostgreSQL because the temporary SlugField and the later unique SlugField alteration both scheduled the same pattern-ops index.
- Fixed by using a temporary CharField during slug backfill, then converting it once to the final unique SlugField.

Current architectural objective:

> Introduce the general Offer model while preserving the existing Product and
> PriceListing comparison core.

Immediate Phase 2 sequence:

1. Add Offer model and offer-type taxonomy.
2. Add optional Product/PriceListing bridges for comparable goods.
3. Backfill existing Pro catalog listings into Offer rows.
4. Add quick-publish flow where website/sale URL is optional.
5. Add public Offer pages and WhatsApp-first CTA.
6. Search Bendango Offers before external web sources.

Last roadmap update: 2026-09-30.
